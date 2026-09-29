# -*- coding: utf-8 -*-
"""
Unity TMP 富文本可视化编辑器 v0.75
依赖: pip install PyQt5
"""

import sys, re, math, json, time, os
import ast as _pyast
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QToolBar, QAction, QLabel, QPlainTextEdit, QDoubleSpinBox,
    QPushButton, QColorDialog, QCheckBox, QScrollArea, QTreeWidget,
    QTreeWidgetItem, QFormLayout, QGroupBox, QFileDialog, QMessageBox,
    QToolButton, QMenu, QInputDialog, QLineEdit, QAbstractItemView,
    QDialog, QSlider, QGridLayout, QSizePolicy, QTableWidget,
    QTableWidgetItem, QHeaderView, QComboBox, QShortcut,
    QListWidget, QListWidgetItem
)
from PyQt5.QtCore import (
    Qt, QPointF, QPoint, QRectF, pyqtSignal, QTranslator, QLibraryInfo,
    QTimer, QEvent, QByteArray, QLineF, QObject
)
from PyQt5.QtGui import (
    QPainter, QColor, QFont, QFontMetricsF, QPen, QBrush,
    QImage, QPolygonF, QGuiApplication, QIcon, QPixmap, QKeySequence,
    QCursor, QValidator, QPainterPath, QTextCursor
)
from PyQt5.QtCore import QLineF
import math as _math

APP_VERSION = u"0.8"

# 引导文件：只记录“设置自动保存是否启用”+“上次选择设置文件路径”
# 每次启动会读取它，自动加载上次的设置文件。
_BOOTSTRAP_FILE = os.path.join(os.path.expanduser("~"),
                               ".tmp_editor_bootstrap.json")


def _load_bootstrap():
    try:
        if os.path.exists(_BOOTSTRAP_FILE):
            with open(_BOOTSTRAP_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return None


def _save_bootstrap(enabled, path):
    try:
        with open(_BOOTSTRAP_FILE, "w", encoding="utf-8") as f:
            json.dump({"enabled": bool(enabled), "path": path or u""},
                      f, ensure_ascii=False)
    except Exception:
        pass


def _geo_to_b64(widget):
    """把 QWidget 的几何状态（位置+尺寸）编码成 base64 字符串"""
    try:
        ba = widget.saveGeometry()
        return bytes(ba.toBase64()).decode("ascii")
    except Exception:
        return None


def _restore_geo(widget, b64):
    """从 base64 字符串还原 QWidget 的几何状态"""
    try:
        if not b64:
            return False
        ba = QByteArray.fromBase64(b64.encode("ascii"))
        return bool(widget.restoreGeometry(ba))
    except Exception:
        return False


# ==================================================================
#                      表达式引擎
# ==================================================================

def _deltaangle(a, b):
    d = (b - a) % 360.0
    if d > 180.0: d -= 360.0
    return d


def _lerp(a, b, t): return a + (b - a) * t


def _inverselerp(a, b, x):
    if abs(b - a) < 1e-12: return 0.0
    return (x - a) / (b - a)


def _lerpangle(a, b, t): return a + _deltaangle(a, b) * t


def _lerpunclamped(a, b, t): return a + (b - a) * t


def _clamp(x, lo, hi): return max(lo, min(hi, x))


def _clamp01(x): return max(0.0, min(1.0, x))


def _pingpong(x, l):
    if l == 0: return 0.0
    x = x % (2 * l)
    if x < 0: x += 2 * l
    return x if x <= l else 2 * l - x


def _repeat(x, l):
    if l == 0: return 0.0
    return x - l * _math.floor(x / l)


def _smoothstep(a, b, t):
    if abs(b - a) < 1e-12: return 0.0
    t = _clamp01((t - a) / (b - a))
    return t * t * (3 - 2 * t)


def _sign(x): return 1 if x > 0 else (-1 if x < 0 else 0)


def _log(x, p):
    if x <= 0 or p <= 0 or abs(p - 1) < 1e-12: return 0.0
    return _math.log(x) / _math.log(p)


def _sin(x):
    v = _math.sin(_math.radians(x))
    return 0.0 if abs(v) < 1e-9 else v


def _cos(x):
    v = _math.cos(_math.radians(x))
    return 0.0 if abs(v) < 1e-9 else v


def _tan(x):
    r = _math.radians(x);
    c = _math.cos(r)
    if abs(c) < 1e-12: return 0.0
    v = _math.sin(r) / c
    return 0.0 if abs(v) < 1e-9 else v


def _asin(x):
    x = max(-1.0, min(1.0, x));
    return _math.degrees(_math.asin(x))


def _acos(x):
    x = max(-1.0, min(1.0, x));
    return _math.degrees(_math.acos(x))


def _atan(x): return _math.degrees(_math.atan(x))


def _atan2(y, x): return _math.degrees(_math.atan2(y, x))


def _truthy(v):
    try:
        return float(v) >= 1.0
    except (TypeError, ValueError):
        return bool(v)


def _ammo(weapon):
    """ammo("武器名") / ammo(SelectedWeapon)

    本工具无法读取游戏内实时弹药，统一返回 0；
    玩家可以在「自定义变量」里起同名变量手动设置弹药量，
    然后在表达式里用 {Ammo_Xxx} 引用。
    """
    try:
        return 0.0
    except Exception:
        return 0.0


def _fmt_num(v):
    if isinstance(v, bool): return '1' if v else '0'
    if isinstance(v, (int, float)):
        if abs(v) < 1e-9: return '0'
        if abs(v - round(v)) < 1e-9: return '%d' % int(round(v))
        s = '%.5f' % v
        s = s.rstrip('0').rstrip('.')
        return s if s else '0'
    return str(v)


def _apply_format(v, fmt):
    fmt = (fmt or "").strip()
    if not fmt: return _fmt_num(v)
    try:
        fv = float(v)
    except Exception:
        return _fmt_num(v)
    m = re.match(r'^[0#]*\.([0#]+)$', fmt)
    if m:
        return '%.*f' % (len(m.group(1)), fv)
    if re.match(r'^[0#]+$', fmt):
        return '%d' % int(round(fv))
    try:
        n = int(fmt)
        if 0 <= n <= 10: return '%.*f' % (n, fv)
    except Exception:
        pass
    return _fmt_num(v)


EXPR_FUNCS = {
    'abs': abs, 'ceil': _math.ceil,
    'clamp': _clamp, 'clamp01': _clamp01,
    'deltaangle': _deltaangle, 'exp': _math.exp,
    'floor': _math.floor, 'inverselerp': _inverselerp,
    'lerp': _lerp, 'lerpangle': _lerpangle,
    'lerpunclamped': _lerpunclamped,
    'log': _log, 'log10': _math.log10,
    'pingpong': _pingpong, 'max': max, 'min': min,
    'pow': pow, 'repeat': _repeat,
    'round': round, 'sign': _sign,
    'smoothstep': _smoothstep, 'sqrt': _math.sqrt,
    'sin': _sin, 'cos': _cos, 'tan': _tan,
    'asin': _asin, 'acos': _acos, 'atan': _atan,
    'atan2': _atan2,
    'pi': _math.pi, 'e': _math.e,
    '_truthy': _truthy,
    'ammo': _ammo,
}

CONTROL_VARS = [
    'Throttle', 'Yaw', 'Brake', 'Pitch', 'Roll',
    'Heading', 'VTOL', 'Trim',
    'LandingGear', 'Brake',
    'FireGuns', 'FireWeapons', 'LaunchCountermeasures',
    'Activate1', 'Activate2', 'Activate3', 'Activate4',
    'Activate5', 'Activate6', 'Activate7', 'Activate8',
]
FLIGHT_VARS = [
    'Altitude', 'AltitudeAgl', 'GS', 'IAS', 'TAS', 'Fuel',
    'AngleOfAttack', 'AngleOfSlip', 'PitchAngle', 'RollAngle',
    'Heading', 'Time', 'GForce', 'VerticalG',
    'Latitude', 'Longitude',
    # ★ 新增
    'PitchRate', 'YawRate', 'RollRate',
    'TargetHeading', 'TargetElevation', 'TargetDistance',
    'TargetSelected',
    'TargetLocked', 'TargetLocking',
    'SelectedWeapon',
]
VARIABLE_NAMES = set(CONTROL_VARS + FLIGHT_VARS + ['Time', 'pi', 'e'])


class _CSEReplacer(_pyast.NodeTransformer):
    def __init__(self, target_key, new_name):
        self.target_key = target_key
        self.new_name = new_name

    def visit(self, node):
        if node is None: return node
        try:
            key = _pyast.unparse(node)
        except Exception:
            key = None
        if key == self.target_key:
            return _pyast.Name(id=self.new_name, ctx=_pyast.Load())
        return self.generic_visit(node)


def _postprocess_cse_defs(defs, texts, max_defs=16, prefix=u'V'):
    """CSE 后处理：
    · 常量定义 (Vx = 5) 和 trivial 定义 (Vx = Vy, Vx = Vy+0, Vx = Vy*1…)
      一律内联回引用处，而不是直接丢弃（避免悬空引用）
    · 若仍超过 max_defs，按净收益从低到高依次内联
    · 最后用 prefix 重编号为 prefix1、prefix2…
    返回:  (new_defs, new_texts)
    """
    if not defs:
        return defs, texts
    prefix = prefix or u'V'

    def _pat(n):
        return re.compile(r'(?<![A-Za-z0-9_])' +
                          re.escape(n) + r'(?![A-Za-z0-9_])')

    def _is_const(s):
        s = (s or u"").strip()
        if not s or len(s) > 500:
            return False
        if re.fullmatch(r'[-+]?\d+(\.\d+)?', s):
            return True
        try:
            v = eval(s, {'__builtins__': {}}, dict(EXPR_FUNCS))
            return isinstance(v, (int, float))
        except Exception:
            return False

    def _trivial_target(s):
        """识别 Vx / Vx+0 / Vx*1 / Vx-0 / Vx/1，返回内层标识符 Vx"""
        s = (s or u"").strip()
        if not s:
            return None
        for _ in range(4):
            m = re.fullmatch(r'\(\s*([^()]*?)\s*\)', s)
            if m:
                s = m.group(1).strip()
                continue
            m = re.fullmatch(
                r'([A-Za-z_][A-Za-z0-9_]*)\s*[+\-]\s*0(?:\.0+)?', s)
            if m:
                s = m.group(1)
                continue
            m = re.fullmatch(
                r'([A-Za-z_][A-Za-z0-9_]*)\s*\*\s*1(?:\.0+)?', s)
            if m:
                s = m.group(1)
                continue
            m = re.fullmatch(
                r'([A-Za-z_][A-Za-z0-9_]*)\s*/\s*1(?:\.0+)?', s)
            if m:
                s = m.group(1)
                continue
            break
        if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', s):
            return s
        return None

    defs1 = list(defs)
    texts1 = list(texts)

    # ---- 1) 迭代内联常量 / trivial 定义 ----
    for _ in range(16):
        inline_map = {}
        keep = []
        for n, e in defs1:
            s = (e or u"").strip()
            if _is_const(s):
                inline_map[n] = s if s else u"0"
            else:
                t = _trivial_target(s)
                if t is not None:
                    inline_map[n] = t
                else:
                    keep.append((n, e))
        if not inline_map:
            break
        names = sorted(inline_map.keys(), key=len, reverse=True)
        pat = re.compile(r'(?<![A-Za-z0-9_])(' +
                         '|'.join(re.escape(x) for x in names) +
                         r')(?![A-Za-z0-9_])')

        def _rep(m):
            v = inline_map.get(m.group(1), u"0")
            return u"(" + v + u")"

        # 迭代替换直到不动点（处理 V3→V5 这类链式引用）
        for _ in range(16):
            nt = [pat.sub(_rep, t) for t in texts1]
            nk = [(n2, pat.sub(_rep, e2)) for n2, e2 in keep]
            if nt == texts1 and nk == keep:
                break
            texts1, keep = nt, nk
        defs1 = keep
        if not defs1:
            return [], texts1

    if not defs1:
        return [], texts1

    # ---- 2) 上限控制（超出 max_defs 时按净收益从小到大内联） ----
    guard = 0
    while len(defs1) > max_defs and guard < 200:
        guard += 1
        cnt = {n: 0 for n, _ in defs1}
        for n2, e2 in defs1:
            for n in cnt:
                if n == n2:
                    continue
                cnt[n] += len(_pat(n).findall(e2))
        for t in texts1:
            for n in cnt:
                cnt[n] += len(_pat(n).findall(t))
        scored = []
        for n, e in defs1:
            net = ((len(e) - len(n)) * cnt.get(n, 0)
                   - (len(e) + len(n) + 2))
            scored.append((net, n, e))
        scored.sort(key=lambda x: x[0])
        _, vn, ve = scored[0]
        pat = _pat(vn)
        repl = u"(" + (ve or u"0") + u")"
        texts1 = [pat.sub(lambda m, r=repl: r, t) for t in texts1]
        defs1 = [(n, pat.sub(lambda m, r=repl: r, e))
                 for n, e in defs1 if n != vn]

    if not defs1:
        return [], texts1

    # ---- 3) 重编号 ----
    remap = {}
    for i, (n, _) in enumerate(defs1, 1):
        remap[n] = u"%s%d" % (prefix, i)
    all_old = list(remap.keys())
    if not all_old:
        return [], texts1
    pat = re.compile(r'(?<![A-Za-z0-9_])(' +
                     '|'.join(re.escape(x) for x in all_old) +
                     r')(?![A-Za-z0-9_])')

    def _ren(m):
        return remap.get(m.group(1), m.group(1))

    defs2 = [(remap[n], pat.sub(_ren, e)) for n, e in defs1]
    texts2 = [pat.sub(_ren, t) for t in texts1]

    return defs2, texts2


class CSEExtractor(object):
    """公共子表达式提取：找重复子树，替换成自定义变量"""

    def __init__(self, prefix=u'V', max_vars=15, min_count=2, min_len=8):
        self.prefix = prefix
        self.max_vars = max_vars
        self.min_count = min_count
        self.min_len = min_len
        self.counter = 0
        self.definitions = []  # [(name, expr), ...]

    def _name(self):
        self.counter += 1
        return u"%s%d" % (self.prefix, self.counter)

    def _peek_name_len(self):
        return len(self.prefix) + len(str(self.counter + 1))

    def _is_candidate(self, node):
        if isinstance(node, (_pyast.Name, _pyast.Constant)):
            return False
        return isinstance(node, (_pyast.BinOp, _pyast.UnaryOp, _pyast.Call,
                                 _pyast.Compare, _pyast.BoolOp, _pyast.IfExp))

    def extract(self, texts):
        trees = []
        for s in texts:
            try:
                trees.append(_pyast.parse(s, mode='eval').body)
            except Exception:
                trees.append(None)

        for _ in range(self.max_vars):
            counts = {};
            samples = {}
            for t in trees:
                if t is None: continue
                for node in _pyast.walk(t):
                    if not self._is_candidate(node): continue
                    try:
                        r = _pyast.unparse(node)
                    except Exception:
                        continue
                    counts[r] = counts.get(r, 0) + 1
                    if r not in samples: samples[r] = node

            best = None;
            best_gain = 0
            vn = self._peek_name_len()
            for r, cnt in counts.items():
                if cnt < self.min_count: continue
                L = len(r)
                if L < self.min_len: continue
                # ★ 定义成本从 +4 降到 +2：边际收益也提取
                gain = (L - vn) * cnt - (L + vn + 2)
                if gain > best_gain:
                    best_gain = gain;
                    best = r
            if best is None: break

            name = self._name()
            self.definitions.append((name, best))
            repl = _CSEReplacer(best, name)
            new_trees = []
            for t in trees:
                if t is None: new_trees.append(None); continue
                new_trees.append(repl.visit(t))
            trees = new_trees

        out = []
        for t in trees:
            if t is None:
                out.append(None)
            else:
                try:
                    out.append(_pyast.unparse(t))
                except Exception:
                    out.append(None)
        return out, list(self.definitions)


RE_BRACE = re.compile(r'\{([^{}]*)\}')

import ast as _ast


class _ExprSimplifier(object):
    def simplify(self, s):
        if not s or not isinstance(s, str): return s
        try:
            tree = _ast.parse(s, mode='eval')
        except Exception:
            return s
        try:
            new = self._visit(tree.body)
        except Exception:
            return s
        try:
            unparse = getattr(_ast, 'unparse', None)
            if unparse is None:
                return s
            return unparse(new)
        except Exception:
            return s

    def _visit(self, node):
        if isinstance(node, _ast.Constant):
            return node
        if isinstance(node, _ast.Name):
            return node
        if isinstance(node, _ast.UnaryOp):
            operand = self._visit(node.operand)
            if isinstance(node.op, _ast.UAdd):
                return operand
            if isinstance(node.op, _ast.USub):
                v = self._const(operand)
                if v is not None:
                    return _ast.Constant(value=-v)
            return _ast.UnaryOp(op=node.op, operand=operand)
        if isinstance(node, _ast.BinOp):
            left = self._visit(node.left)
            right = self._visit(node.right)
            lv = self._const(left);
            rv = self._const(right)
            if lv is not None and rv is not None:
                v = self._calc(lv, rv, node.op)
                if v is not None:
                    return _ast.Constant(value=v)
            if isinstance(node.op, _ast.Add):
                if lv == 0: return right
                if rv == 0: return left
                if isinstance(right, _ast.UnaryOp) and isinstance(right.op, _ast.USub):
                    return _ast.BinOp(left=left, op=_ast.Sub(), right=right.operand)
            elif isinstance(node.op, _ast.Sub):
                if rv == 0: return left
                if lv == 0:
                    return _ast.UnaryOp(op=_ast.USub(), operand=right)
            elif isinstance(node.op, _ast.Mult):
                if lv == 0 or rv == 0: return _ast.Constant(value=0)
                if lv == 1: return right
                if rv == 1: return left
            elif isinstance(node.op, _ast.Div):
                if rv == 1: return left
            elif isinstance(node.op, _ast.Pow):
                if rv == 1: return left
            return _ast.BinOp(left=left, op=node.op, right=right)
        if isinstance(node, _ast.Call):
            args = [self._visit(a) for a in node.args]
            fname = node.func.id if isinstance(node.func, _ast.Name) else None
            if fname and fname in EXPR_FUNCS and args:
                vals = [self._const(a) for a in args]
                if all(v is not None for v in vals):
                    try:
                        v = EXPR_FUNCS[fname](*vals)
                        if isinstance(v, (int, float)):
                            return _ast.Constant(value=v)
                    except Exception:
                        pass
            return _ast.Call(func=node.func, args=args, keywords=[])
        if isinstance(node, _ast.IfExp):
            return _ast.IfExp(test=self._visit(node.test),
                              body=self._visit(node.body),
                              orelse=self._visit(node.orelse))
        if isinstance(node, _ast.Compare):
            return _ast.Compare(left=self._visit(node.left),
                                ops=node.ops,
                                comparators=[self._visit(c) for c in node.comparators])
        if isinstance(node, _ast.BoolOp):
            return _ast.BoolOp(op=node.op,
                               values=[self._visit(v) for v in node.values])
        return node

    def _const(self, node):
        if isinstance(node, _ast.Constant):
            v = node.value
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return v
        return None

    def _calc(self, a, b, op):
        try:
            if isinstance(op, _ast.Add): return a + b
            if isinstance(op, _ast.Sub): return a - b
            if isinstance(op, _ast.Mult): return a * b
            if isinstance(op, _ast.Div): return a / b
            if isinstance(op, _ast.Pow): return a ** b
        except Exception:
            pass
        return None


_EXPR_SIMPLIFIER = _ExprSimplifier()


def simplify_expr(s):
    return _EXPR_SIMPLIFIER.simplify(s)


def _convert_ternary(expr):
    expr = expr.strip()
    depth = 0;
    q_pos = -1
    for i, ch in enumerate(expr):
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        elif ch == '?' and depth == 0:
            q_pos = i;
            break
    if q_pos == -1: return expr
    depth = 0;
    c_pos = -1
    for i in range(q_pos + 1, len(expr)):
        ch = expr[i]
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        elif ch == ':' and depth == 0:
            c_pos = i;
            break
    if c_pos == -1: return expr
    cond = expr[:q_pos].strip()
    tp = expr[q_pos + 1:c_pos].strip()
    fp = expr[c_pos + 1:].strip()
    return "(%s if _truthy(%s) else %s)" % (
        _convert_ternary(tp), _convert_ternary(cond), _convert_ternary(fp))


def preprocess_expr(expr):
    expr = _convert_ternary(expr)
    expr = re.sub(r'(?<![&])&(?![&])', ' and ', expr)
    expr = re.sub(r'(?<![|])\|(?![|])', ' or ', expr)
    return expr


class ExprState(object):
    def __init__(self): self.data = {}


def eval_text_stateful(text, variables, dt, state, item_id=None):
    if not text or '{' not in text: return text
    # ★ 长文本保护：超过 10KB 直接原样返回（防正则/递归爆炸）
    if len(text) > 10000:
        return text

    def sub(m):
        expr_str = m.group(1).strip()
        if not expr_str: return ''
        es = expr_str.strip()
        if len(es) >= 2 and es.startswith('"') and es.endswith('"'):
            return es[1:-1]
        depth = 0;
        in_str = False;
        semi_pos = -1
        for i, ch in enumerate(expr_str):
            if ch == '"':
                in_str = not in_str
            elif in_str:
                continue
            elif ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            elif ch == ';' and depth == 0:
                semi_pos = i;
                break
        fmt = None
        if semi_pos >= 0:
            fmt = expr_str[semi_pos + 1:].strip()
            expr_str = expr_str[:semi_pos].strip()
            if not expr_str: return ''
        block_pos = m.start()
        counters = {}

        def next_idx(name):
            i = counters.get(name, 0);
            counters[name] = i + 1;
            return i

        env = dict(EXPR_FUNCS);
        env.update(variables)

        def sum_fn(x):
            i = next_idx('sum');
            k = ('sum', item_id, block_pos, i)
            t = float(variables.get('Time', 0.0))
            last = state.data.get(k)
            if last is None:
                state.data[k] = (0.0, t)
                return 0.0
            lv, lt = last
            if t < lt:  # 时间被重置
                lv = 0.0;
                lt = t
            v = lv + float(x) * max(0.0, t - lt)
            state.data[k] = (v, t)
            return v

        def rate_fn(x):
            i = next_idx('rate');
            k = ('rate', item_id, block_pos, i)
            t = float(variables.get('Time', 0.0))
            last = state.data.get(k)
            if last is None or abs(t - last[1]) < 1e-9:
                state.data[k] = (float(x), t)
                return 0.0
            r = (float(x) - last[0]) / (t - last[1])
            state.data[k] = (float(x), t)
            return r

        def smooth_fn(x, r):
            i = next_idx('smooth');
            k = ('smooth', item_id, block_pos, i)
            t = float(variables.get('Time', 0.0))
            x = float(x);
            r = abs(float(r))
            last = state.data.get(k)
            if last is None:
                state.data[k] = (x, t)
                return x
            cur, lt = last
            if t < lt: lt = t
            step = r * (t - lt)
            if x > cur:
                cur = min(x, cur + step)
            else:
                cur = max(x, cur - step)
            state.data[k] = (cur, t)
            return cur

        def pid_fn(target, current, p, i_, d):
            idx = next_idx('pid')
            t = float(variables.get('Time', 0.0))
            ki = ('pid_i', item_id, block_pos, idx)
            kp = ('pid_p', item_id, block_pos, idx)
            kt = ('pid_t', item_id, block_pos, idx)
            target = float(target);
            current = float(current)
            err = target - current
            last_t = state.data.get(kt, t)
            delta_t = max(0.0, t - last_t)
            integral = state.data.get(ki, 0.0) + err * delta_t
            prev_err = state.data.get(kp, err)
            deriv = (err - prev_err) / delta_t if delta_t > 1e-9 else 0.0
            state.data[ki] = integral;
            state.data[kp] = err;
            state.data[kt] = t
            return float(p) * err + float(i_) * integral + float(d) * deriv

        env['sum'] = sum_fn;
        env['rate'] = rate_fn
        env['smooth'] = smooth_fn;
        env['PID'] = pid_fn

        py = preprocess_expr(expr_str)
        try:
            r = eval(py, {'__builtins__': {}}, env)
        except Exception:
            return m.group(0)
        if fmt is not None: return _apply_format(r, fmt)
        return _fmt_num(r)

    return RE_BRACE.sub(sub, text)


def has_expr(text): return bool(text) and '{' in text and '}' in text


# ==================================================================
#                      富文本标签解析
# ==================================================================

RE_TAG = re.compile(r'<(/?)([a-zA-Z\-]+)(?:=([^>]*))?/?>')


def _parse_size_arg(arg):
    """解析 <size=X> 的参数。
    · "X%" → X/100（例如 35% → 0.35）
    · "X"   → X
    · 非法 → 1.0
    """
    s = (arg or u"").strip()
    if s.endswith('%'):
        try:
            return float(s[:-1]) / 100.0
        except Exception:
            return 1.0
    try:
        return float(s)
    except Exception:
        return 1.0


def _fix_space_marks(result):
    """修正空格上的 mark：
    · 只有当一个空格左右两侧都存在"非空格且带 mark"的字符时，
      才保留它身上的 mark（这样 mark 才能覆盖空格区域）
    · 否则清掉这个空格的 mark（让它单纯作为空隙）
    """
    try:
        n = len(result)
        for i in range(n):
            ch, st = result[i]
            if ch != ' ' or st.get('mark') is None:
                continue
            # 向左找第一个非空格
            left_ok = False
            for j in range(i - 1, -1, -1):
                ch2, st2 = result[j]
                if ch2 == ' ':
                    continue
                left_ok = (st2.get('mark') is not None)
                break
            # 向右找第一个非空格
            right_ok = False
            for j in range(i + 1, n):
                ch2, st2 = result[j]
                if ch2 == ' ':
                    continue
                right_ok = (st2.get('mark') is not None)
                break
            if not (left_ok and right_ok):
                st['mark'] = None
    except Exception:
        pass
    return result


def parse_rich_tags(text, variables=None):
    if variables is None:
        variables = {}

    def resolve_arg(arg):
        if arg is None: return None
        s = arg.strip()
        if not s: return s

        def sub_expr(m):
            expr = m.group(1).strip()
            if not expr: return ''
            py = preprocess_expr(expr)
            env = dict(EXPR_FUNCS);
            env.update(variables)
            try:
                r = eval(py, {'__builtins__': {}}, env)
            except Exception:
                return m.group(0)
            return _fmt_num(r)

        return RE_BRACE.sub(sub_expr, s)

    base_state = {
        'size': 1.0, 'color': None, 'rotate': 0.0, 'alpha': 1.0,
        'pos': 0.0, 'voffset': 0.0, 'bold': False, 'italic': False,
        'scale': 1.0, 'cspace': 0.0, 'mspace': 0.0,
        'underline': False, 'strike': False,
        'sup': False, 'sub': False,
        'lowercase': False, 'uppercase': False, 'smallcaps': False,
        'mark': None,
        'mark_alpha': 1.0,
    }
    state = dict(base_state);
    stack = [];
    result = []
    pos = 0
    for m in RE_TAG.finditer(text):
        for ch in text[pos:m.start()]:
            result.append((ch, dict(state)))
        closing = (m.group(1) == '/')
        name = m.group(2).lower()
        arg = resolve_arg(m.group(3))
        if closing:
            if stack: state = stack.pop()
            pos = m.end()
            continue
        if name == 'br':
            result.append(('\n', dict(state)))
            pos = m.end();
            continue
        if name == 'nobr':
            pos = m.end();
            continue
        stack.append(dict(state))
        try:
            if name == 'size' and arg:
                state['size'] = _parse_size_arg(arg)
            elif name == 'color' and arg:
                s = arg if arg.startswith('#') else ('#' + arg)
                c = QColor(s)
                if c.isValid(): state['color'] = c
            elif name == 'rotate' and arg:
                state['rotate'] = float(arg)
            elif name == 'alpha' and arg:
                a = int(arg.lstrip('#'), 16) / 255.0
                state['alpha'] = max(0.0, min(1.0, a))
            elif name == 'pos' and arg:
                state['pos'] = float(arg)
            elif name == 'voffset' and arg:
                state['voffset'] = float(arg)
            elif name == 'scale' and arg:
                state['scale'] = float(arg)
            elif name == 'cspace' and arg:
                state['cspace'] = float(arg)
            elif name == 'mspace' and arg:
                state['mspace'] = float(arg)
            elif name == 'space' and arg:
                try:
                    # ★ 用"相对字号"的宽度，不用字体度量值，
                    #   避免缩放时字体 hinting 导致的宽度抖动
                    #   space=n → n*2 个普通字符宽 → n*2 em
                    SPACE_CORRECTION = 5.24 / 9.6
                    n = float(arg)
                    if n < 0:
                        n = 0.0
                    st_copy = dict(state)
                    st_copy['space_width_em'] = n * 2.0 * SPACE_CORRECTION
                    result.append((' ', st_copy))
                except Exception:
                    pass
                stack.pop();
                pos = m.end();
                continue
            elif name == 'mark' and arg:
                s = arg if arg.startswith('#') else ('#' + arg)
                c = QColor(s)
                if c.isValid():
                    state['mark'] = c
                    # ★ mark 背景的透明度 = 应用 mark 时"外层"的 alpha
                    #   之后内层再出现 <alpha> 不影响它
                    state['mark_alpha'] = state['alpha']
            elif name == 'b':
                state['bold'] = True
            elif name == 'i':
                state['italic'] = True
            elif name == 'u':
                state['underline'] = True
            elif name == 's':
                state['strike'] = True
            elif name == 'sup':
                state['sup'] = True
            elif name == 'sub':
                state['sub'] = True
            elif name == 'lowercase':
                state['lowercase'] = True
            elif name == 'uppercase':
                state['uppercase'] = True
            elif name == 'smallcaps':
                state['smallcaps'] = True
        except Exception:
            pass
        pos = m.end()
    for ch in text[pos:]:
        result.append((ch, dict(state)))
    return _fix_space_marks(result)


# ==================================================================
#                      字形校正模块
# ==================================================================

def _circle_out_vo(c, g):
    return 0.45 * g - 0.4 * c if c <= g else 0.9 * g - 0.825 * c + 0.05


def _dash_out_vo(c, g):
    return 0.45 * g - 0.415 * c + 0.01 if c <= g else 0.9 * g - 0.833333 * c + 0.033333


def _circle_canvas_up(c):
    return 0.015 * c * c + 0.04


def _triangle_up_out_vo(c, g):
    return 0.3474 * g - 0.2927 * c


def _solid_circle_out_vo(c, g):
    return 0.34668 * g - 0.28308 * c


GLYPH_CORRECTIONS = {
    u"○": {
        "out_vo_fn": lambda c, g: 0.3466667 * g - 0.3 * c,
        "out_vo_str": u"0.3466667*{G}-0.3*{C}",
        "disp_scale": 23.22 / 22.5,
        "disp_up_vo_fn": lambda eff: 2.7 * (eff / 23.22),
    },
    u"─": {
        "out_vo_fn": _dash_out_vo,
        "out_vo_str": u"0.45*{G}-0.415*{C}+0.01",
    },
    u"▲": {
        "out_vo_fn": _triangle_up_out_vo,
        "out_vo_str": u"0.3474*{G}-0.2927*{C}",
        "disp_scale": 14.43 / 17.0,
        "disp_up_vo_fn": lambda eff: 0.745 * (eff / 14.43),
        "disp_pos_fn": lambda eff: -0.01 * (eff / 14.43),
        "out_pos_str": u"-0.01*({C})/17.0",
    },
    u"●": {
        "out_vo_fn": lambda c, g: 0.3466667 * g - 0.3 * c,
        "out_vo_str": u"0.3466667*{G}-0.3*{C}",
        "disp_scale": 23.22 / 22.5,
        "disp_up_vo_fn": lambda eff: 2.7 * (eff / 23.22),
    },

    u"■": {
        "disp_scale": 21.69 / 20.7,
        "disp_up_vo_fn": lambda eff: 3.64 * (eff / 21.69),
        "disp_pos_fn": lambda eff: 0.007 * (eff / 21.69),
        # ★ 输出矫正：vo = (26/75)·G − 0.3·C
        "out_vo_fn": lambda c, g: (26.0 / 75.0) * g - 0.3 * c,
        "out_vo_str": u"0.3466667*{G}-0.3*{C}",
    },
}


def _wrap_expr(s):
    s = (s or "").strip()
    if s.startswith('{') and s.endswith('}'):
        return s
    return '{' + s + '}'


def _unwrap_expr(s):
    s = (s or "").strip()
    if s.startswith('{') and s.endswith('}'):
        return s[1:-1]
    return s


def _add_to_expr(base_field, extra_expr):
    """把 extra_expr 加到 base_field 上，返回 {xxx+yyy} 形式。
    若内层含顶层 ;fmt 格式后缀，则把后缀移到末尾，避免
    {expr;fmt+补偿} 这类无效语法把补偿吞掉。"""
    inner = _unwrap_expr(base_field)
    # 找顶层 ; （跳过括号内 / 字符串内）
    depth = 0
    in_str = False
    semi_pos = -1
    for i, ch in enumerate(inner):
        if ch == '"':
            in_str = not in_str
        elif in_str:
            continue
        elif ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        elif ch == ';' and depth == 0:
            semi_pos = i
            break
    if semi_pos >= 0:
        expr_part = inner[:semi_pos]
        fmt_part = inner[semi_pos:]
    else:
        expr_part = inner
        fmt_part = ''
    return '{' + expr_part + '+' + extra_expr + fmt_part + '}'


def _plain_text_out_vo(c, g):
    if abs(g - c) < 1e-9: return 0.0
    return 0.345 * (g - c)


def get_out_vo(text, cs, gs, ch, gr):
    info = GLYPH_CORRECTIONS.get(text)
    if info is not None and "out_vo_fn" in info:
        return info["out_vo_fn"](cs, gs)
    return _plain_text_out_vo(cs, gs)


def get_canvas_up_world(text, cs):
    info = GLYPH_CORRECTIONS.get(text)
    if info is None or "canvas_up_fn" not in info: return 0.0
    return info["canvas_up_fn"](cs)


# ---------------------------------------------------------------- 常量
FONT_SIZE_UNIT = 0.1
DEFAULT_FONT_FAMILY = u"Microsoft YaHei"
OUT_PREFIX = u"<line-height=0><voffset=0> </voffset>"
OUT_SUFFIX = u"<voffset=0> </voffset>"
DEFAULT_COLOR = QColor("#000000")
DEFAULT_GLOBAL_SIZE = 1.0
DEFAULT_GLYPH_RATIO = 0.2
POS_PER_WORLD = 20.0
VO_PER_WORLD = 10.0
POS_HALF_PER_CANVAS = 10.0
VO_HALF_PER_CANVAS = 5.0
PLAIN_DRAW_SCALE = 13.22 / 14.5
PLAIN_DRAW_UP_VO_PER_SIZE = 0.02
RULER_SIZE = 22
# ==================================================================
#                      语言文本
# ==================================================================

LANG_TEXTS = {
    'zh': {
        'title': u'Unity TMP 富文本可视化编辑器',
        'lang_label': u'语言', 'menu_ctrl': u'🎛 控制面板',
        'float_btn': u'↗ 独立窗口', 'dock_btn': u'↙ 合并回主窗',
        'float_title': u'控制面板（独立窗口）',
        'output_title': u'输出：',
        'char_table': u'字符选择表', 'add_char': u'＋ 添加字符',
        'duplicate': u'⧉ 复制', 'delete': u'🗑 删除',
        'insert_sym': u'插入符号',
        'canvas_w': u'  画布 W:', 'canvas_h': u' H:',
        'global_size': u'  全局大小:', 'fit_view': u'适应窗口',
        'grid_spacing': u'  网格间距: ', 'more': u'⚙ 更多',
        'var_list': u'📋 变量列表', 'flight_data': u'✈ 飞行数据模拟',
        'import_rich': u'导入富文本', 'export_png': u'导出 PNG',
        'save_proj': u'保存工程', 'open_proj': u'打开工程',
        'save_settings': u'保存设置',
        'show_grid': u'显示网格', 'snap_grid': u'网格吸附',
        'show_bounds': u'显示方框', 'show_ruler': u'显示标尺',
        'auto_refresh': u'自动刷新',
        'regen': u'重新生成', 'copy': u'复制',
        'minimize': u'▼ 最小化', 'expand': u'▲ 展开',
        'style': u'样式', 'char_size': u'缩放',
        'rotate': u'旋转', 'bold_italic': u'字形',
        'color': u'color', 'coords': u'坐标 (pos / voffset)',
        'pos': u'pos', 'voffset': u'voffset',
        'content': u'文本内容', 'preview': u'预览:',
        'insert_var': u'插入变量', 'insert_fn': u'插入函数',
        'insert_preset': u'插入预设', 'add_char_btn': u'添加字符',
        'new_folder': u'＋文件夹', 'rename': u'重命名', 'del': u'删除',
        'dual': u'⇋ 双排', 'single': u'⇋ 单排',
        'move_up': u'↑ 上移', 'move_down': u'↓ 下移',
        'share': u'分享', 'import': u'导入',
        'var_list_title': u'变量列表（当前值）',
        'var_list_hint': u'以下是可用变量名与当前值：',
        'var_name_col': u'变量名', 'cur_val_col': u'当前值',
        'copy_all': u'复制全部', 'close': u'关闭', 'copied': u'已复制 ✓',
        'flight_title': u'飞行数据模拟', 'flight_data_btn': u'✈ 飞行数据',
        'flight_hint': u'', 'ok': u'确定', 'cancel': u'取消',
        'share_title': u'分享字符表',
        'share_hint': u'下面是导出的 JSON 文本，可复制保存或分享：',
        'copy_clip': u'复制到剪贴板',
        'import_title': u'导入字符表',
        'import_hint': u'粘贴分享得到的 JSON 文本：',
        'import_ok': u'导入并替换', 'hint': u'提示',
        'empty_content': u'内容为空。', 'fail': u'失败',
        'json_fail': u'JSON 解析失败：', 'no_root': u'缺少 root 字段。',
        'import_rich_title': u'导入 Unity TMP 富文本',
        'import_rich_hint': u'粘贴一段富文本：',
        'no_element': u'没有解析到有效元素。',
        'export_png_title': u'导出 PNG',
        'export_png_filter': u'PNG (*.png)',
        'export_res_title': u'导出分辨率',
        'export_res_hint': u'每世界单位像素数:',
        'save_title': u'保存工程', 'save_filter': u'JSON (*.json)',
        'open_title': u'打开工程', 'save_done': u'工程已保存',
        'loaded': u'工程已加载', 'save_fail': u'保存失败',
        'img_fail': u'图片保存失败。', 'no_canvas': u'画布为空。',
        'float_hint': u'请先展开输出窗口，再独立控制面板。',
        'reset_all': u'全部重置', 'reset_one': u'重置',
        'ctrl_section': u'控制变量', 'flight_section': u'飞行数据',
        'aoa': u'AoA', 'speed': u'速度',
        'run_test': u'运行测试',
        'hide_show': u'隐藏/显示',
        'no_selection': u'请先在字符表里选中条目。',
        'snap_grid': u'吸附网格', 'char_snap': u'字符吸附',
        'lock_helpers': u'固定辅助线',
        'bind_btn': u'吸附', 'unbind_btn': u'分离',
        'unbind_all_btn': u'分离所有',
        'custom_vars_hdr': u'自定义变量 / 函数',
        'col_var': u'变量名', 'col_expr': u'表达式',
        'copy_btn': u'复制',
        'choose_color': u'选择颜色',
        'bind_ctl_title': u'吸附控制方式',
        'helpers_menu': u'辅助线',
        'point_lbl': u'点', 'line_lbl': u'线', 'circle_lbl': u'圆',
        'parent_not_line': u'父对象不是辅助线，无法使用此模式',
        'parent_not_circle': u'父对象不是辅助圆，无法使用此模式',
        'new_folder_dlg': u'新建文件夹',
        'rename_folder_dlg': u'重命名文件夹',
        'rename_helper_dlg': u'重命名辅助对象',
        'name_label': u'名称：',
        'new_name_label': u'新名称：',
        'default_folder_name': u'新文件夹',
        'custom_vars_title': u'自定义函数',
        'custom_vars_btn': u'自定义变量',
        'target_ctrl_btn': u'目标控制',
        'target_ctrl_title': u'目标控制',
        'reset_target_params': u'重置目标参数',
        'reset_player_params': u'重置主机体参数',
        'custom_vars_menu': u'📋 自定义变量',
        'custom_vars_hdr': u'自定义函数',
        'cse_low': u'低',
        'cse_mid': u'中',
        'cse_high': u'高',
        'cse_tip': u'压缩程度',
        'cse_label': u'压缩程度：',
    },
    'en': {
        'title': u'Unity TMP Rich Text Editor',
        'lang_label': u'Lang', 'menu_ctrl': u'🎛 Control Panel',
        'float_btn': u'↗ Float Window', 'dock_btn': u'↙ Dock Back',
        'float_title': u'Control Panel (Floating)',
        'output_title': u'Output:',
        'char_table': u'Char List', 'add_char': u'+ Add Char',
        'duplicate': u'⧉ Duplicate', 'delete': u'🗑 Delete',
        'insert_sym': u'Insert Symbol',
        'canvas_w': u'  Canvas W:', 'canvas_h': u' H:',
        'global_size': u'  Font Size:', 'fit_view': u'Fit View',
        'grid_spacing': u'  Grid Spacing: ', 'more': u'⚙ More',
        'var_list': u'📋 Variable List', 'flight_data': u'✈ Flight Data',
        'import_rich': u'Import Rich Text', 'export_png': u'Export PNG',
        'save_proj': u'Save Project', 'open_proj': u'Open Project',
        'save_settings': u'Save Settings',
        'show_grid': u'Show Grid', 'snap_grid': u'Snap Grid',
        'show_bounds': u'Show Bounds', 'show_ruler': u'Show Ruler',
        'auto_refresh': u'Auto Refresh',
        'regen': u'Regenerate', 'copy': u'Copy',
        'minimize': u'▼ Minimize', 'expand': u'▲ Expand',
        'style': u'Style', 'char_size': u'Size',
        'rotate': u'Rotate', 'bold_italic': u'Font Style',
        'color': u'color', 'coords': u'Coords (pos / voffset)',
        'pos': u'pos', 'voffset': u'voffset',
        'content': u'Text Content', 'preview': u'Preview:',
        'insert_var': u'Insert Var', 'insert_fn': u'Insert Fn',
        'insert_preset': u'Insert Preset', 'add_char_btn': u'Add Char',
        'new_folder': u'+ Folder', 'rename': u'Rename', 'del': u'Delete',
        'dual': u'⇋ Dual', 'single': u'⇋ Single',
        'move_up': u'↑ Up', 'move_down': u'↓ Down',
        'share': u'Share', 'import': u'Import',
        'var_list_title': u'Variable List (Current)',
        'var_list_hint': u'Available variables and current values:',
        'var_name_col': u'Variable', 'cur_val_col': u'Value',
        'copy_all': u'Copy All', 'close': u'Close', 'copied': u'Copied ✓',
        'flight_title': u'Flight Data Simulation',
        'flight_data_btn': u'✈ Flight Data',
        'flight_hint': u'', 'ok': u'OK', 'cancel': u'Cancel',
        'share_title': u'Share Char List',
        'share_hint': u'JSON text below, copy or share:',
        'copy_clip': u'Copy to Clipboard',
        'import_title': u'Import Char List',
        'import_hint': u'Paste the JSON text:',
        'import_ok': u'Import & Replace', 'hint': u'Info',
        'empty_content': u'Content is empty.', 'fail': u'Failed',
        'json_fail': u'JSON parse failed: ', 'no_root': u'Missing root field.',
        'import_rich_title': u'Import Unity TMP Rich Text',
        'import_rich_hint': u'Paste rich text:',
        'no_element': u'No valid element found.',
        'export_png_title': u'Export PNG',
        'export_png_filter': u'PNG (*.png)',
        'export_res_title': u'Export Resolution',
        'export_res_hint': u'Pixels per world unit:',
        'save_title': u'Save Project', 'save_filter': u'JSON (*.json)',
        'open_title': u'Open Project', 'save_done': u'Project saved',
        'loaded': u'Project loaded', 'save_fail': u'Save failed',
        'img_fail': u'Failed to save image.', 'no_canvas': u'Canvas is empty.',
        'float_hint': u'Please expand the output panel first.',
        'reset_all': u'Reset All', 'reset_one': u'Reset',
        'ctrl_section': u'Control Variables', 'flight_section': u'Flight Data',
        'aoa': u'AoA', 'speed': u'Speed',
        'run_test': u'Run Test',
        'hide_show': u'Hide/Show',
        'no_selection': u'Please select items in the char list first.',
        'snap_grid': u'Snap Grid', 'char_snap': u'Char Snap',
        'lock_helpers': u'Lock Helpers',
        'bind_btn': u'Bind', 'unbind_btn': u'Unbind',
        'unbind_all_btn': u'Unbind All',
        'custom_vars_hdr': u'Custom Vars / Functions',
        'col_var': u'Var', 'col_expr': u'Expr',
        'copy_btn': u'Copy',
        'choose_color': u'Choose Color',
        'bind_ctl_title': u'Binding Mode',
        'helpers_menu': u'Helpers',
        'point_lbl': u'Point', 'line_lbl': u'Line', 'circle_lbl': u'Circle',
        'parent_not_line': u'Parent is not a helper line, cannot use this mode',
        'parent_not_circle': u'Parent is not a helper circle, cannot use this mode',
        'new_folder_dlg': u'New Folder',
        'rename_folder_dlg': u'Rename Folder',
        'rename_helper_dlg': u'Rename Helper',
        'name_label': u'Name:',
        'new_name_label': u'New name:',
        'default_folder_name': u'New Folder',
        'custom_vars_title': u'Variables',
        'custom_vars_btn': u'Variable Outputs',
        'target_ctrl_btn': u'Target Control',
        'target_ctrl_title': u'Target Control',
        'reset_target_params': u'Reset target params',
        'reset_player_params': u'Reset player params',
        'custom_vars_menu': u'📋 Variable Outputs',
        'custom_vars_hdr': u'Variables',
        'cse_low': u'Low',
        'cse_mid': u'Mid',
        'cse_high': u'High',
        'cse_tip': u'Compression level',
        'cse_label': u'Compression:',
    },
}
CURRENT_LANG = 'zh'
def _T(key):
    return LANG_TEXTS.get(CURRENT_LANG, LANG_TEXTS['zh']).get(key, key)

def _L(zh, en):
    """运行时选择中/英字符串"""
    return zh if CURRENT_LANG == 'zh' else en


ZH_EN_MAP = {
    u"＋ 添加字符": u"+ Add Char",
    u"⧉ 复制": u"⧉ Duplicate",
    u"🗑 删除": u"🗑 Delete",
    u"插入符号": u"Insert Symbol",
    u"适应窗口": u"Fit View", u"⚙ 更多": u"⚙ More",
    u"📋 变量列表": u"📋 Variable List",
    u"✈ 飞行数据模拟": u"✈ Flight Data",
    u"📋 自定义变量": u"📋 Variable Outputs",
    u"导入富文本": u"Import Rich Text",
    u"导出 PNG": u"Export PNG",
    u"保存工程": u"Save Project", u"打开工程": u"Open Project",
    u"显示网格": u"Show Grid", u"网格吸附": u"Snap Grid",
    u"显示方框": u"Show Bounds", u"显示标尺": u"Show Ruler",
    u"🎛 控制面板": u"🎛 Control Panel",
    u"语言": u"Lang",
    u"  画布 W:": u"  Canvas W:",
    u" H:": u" H:",
    u"  全局大小:": u"  Font Size:",
    u"全局大小 G:": u"Font Size:",
    u"全局大小:": u"Font Size:",
    u"  网格间距: ": u"  Grid Spacing: ",
    u"网格间距: ": u"Grid Spacing: ",
    u"选择颜色": u"Choose Color",
    u"已复制到剪贴板": u"Copied to clipboard",
    u"沿辅助圆旋转": u"Rotate on Helper Circle",
    u"沿辅助线滑动": u"Slide on Helper Line",
    u"控制变量（0~1 绕一圈）：": u"Control variable (0~1 for full turn):",
    u"控制变量（0=起点, 1=终点）：": u"Control variable (0=start, 1=end):",
    u"画布上没有辅助圆": u"No helper circle on canvas",
    u"画布上没有辅助线": u"No helper line on canvas",
    u"Unity TMP 富文本输出：": u"Unity TMP Rich Text Output:",
    u"自动刷新": u"Auto Refresh", u"重新生成": u"Regenerate",
    u"复制": u"Copy", u"▼ 最小化": u"▼ Minimize", u"▲ 展开": u"▲ Expand",
    u"↗ 独立窗口": u"↗ Float Window", u"↙ 合并回主窗": u"↙ Dock Back",
    u"文本内容": u"Text Content", u"样式": u"Style",
    u"缩放": u"Size",
    u"旋转": u"Rotate",
    u"字形": u"Font Style",
    u"文字颜色（默认 #000000）": u"Color (default #000000)",
    u"坐标 (pos / voffset)": u"Coords (pos / voffset)",
    u"预览:": u"Preview:", u"插入变量": u"Insert Var",
    u"插入函数": u"Insert Fn",
    u"插入预设": u"Insert Preset",
    u"添加字符": u"Add Char",
    u"字符选择表": u"Char List",
    u"＋文件夹": u"+ Folder", u"重命名": u"Rename", u"删除": u"Delete",
    u"⇋ 双排": u"⇋ Dual", u"⇋ 单排": u"⇋ Single",
    u"↑ 上移": u"↑ Up", u"↓ 下移": u"↓ Down",
    u"分享": u"Share", u"导入": u"Import",
    u"控制面板（独立窗口）": u"Control Panel (Floating)",
    u"↺ 全部重置": u"↺ Reset All",
    u"确定": u"OK", u"取消": u"Cancel", u"关闭": u"Close",
    u"控制变量": u"Control Variables", u"飞行数据": u"Flight Data",
    u"✈ 飞行数据": u"✈ Flight Data",
    u"运行测试": u"Run Test",
    u"辅助线": u"Helpers",
    u"吸附网格": u"Snap Grid",
    u"字符吸附": u"Char Snap",
    u"固定辅助线": u"Lock Helpers",
    u"吸附": u"Bind",
    u"分离": u"Unbind",
    u"分离所有": u"Unbind All",
    u"隐藏/显示": u"Hide/Show",
    u"自定义变量 / 函数": u"Custom Vars / Functions",
    u"变量名": u"Var",
    u"表达式": u"Expr",
    u"复制": u"Copy",
    u"保存设置": u"Save Settings",
}
EN_ZH_MAP = {v: k for k, v in ZH_EN_MAP.items()}


# ================================================================ 树节点
def _helper_bind_dialog_dict(obj):
    """导出吸附对话框的元信息（点 / 线 / 圆 通用）"""
    return {
        "bind_dialog_mode": getattr(obj, '_bind_dialog_mode', None),
        "bind_dialog_ctrl": getattr(obj, '_bind_dialog_ctrl', None),
        "bind_dialog_t0": getattr(obj, '_bind_dialog_t0', None),
        "bind_dialog_t1": getattr(obj, '_bind_dialog_t1', None),
        "bind_dialog_tangent": getattr(obj, '_bind_dialog_tangent', None),
        "bind_dialog_reverse": getattr(obj, '_bind_dialog_reverse', None),
        "bind_dialog_start_angle": getattr(obj, '_bind_dialog_start_angle', None),
        "bind_dialog_obj_offset": getattr(obj, '_bind_dialog_obj_offset', None),
    }


def _helper_restore_bind_dialog(obj, d):
    """从字典恢复吸附对话框的元信息"""
    try:
        if d.get("bind_dialog_mode") is not None:
            obj._bind_dialog_mode = d["bind_dialog_mode"]
        if d.get("bind_dialog_ctrl") is not None:
            obj._bind_dialog_ctrl = d["bind_dialog_ctrl"]
        if d.get("bind_dialog_t0") is not None:
            obj._bind_dialog_t0 = float(d["bind_dialog_t0"])
        if d.get("bind_dialog_t1") is not None:
            obj._bind_dialog_t1 = float(d["bind_dialog_t1"])
        if d.get("bind_dialog_tangent") is not None:
            obj._bind_dialog_tangent = bool(d["bind_dialog_tangent"])
        if d.get("bind_dialog_reverse") is not None:
            obj._bind_dialog_reverse = bool(d["bind_dialog_reverse"])
        if d.get("bind_dialog_start_angle") is not None:
            obj._bind_dialog_start_angle = float(d["bind_dialog_start_angle"])
        if d.get("bind_dialog_obj_offset") is not None:
            obj._bind_dialog_obj_offset = float(d["bind_dialog_obj_offset"])
    except Exception:
        pass


class Node(object):
    def __init__(self, name=u"", folder=False, item=None, helper=None, parent=None):
        self.name = name;
        self.folder = folder
        self.item = item
        self.helper = helper
        self.children = [];
        self.parent = parent
        self.dual_side = None

    def is_root(self): return self.parent is None


class HelperPoint(object):
    def __init__(self, x=0.0, y=0.0, name=u""):
        self.name = name
        self.x = x;
        self.y = y
        self.visible = True
        self.group_id = None
        self.bind_to = u""
        self.bind_dx = 0.0;
        self.bind_dy = 0.0;
        self.bind_angle = 0.0
        self.expr_x = u"";
        self.expr_y = u""
        self.use_expr_x = False;
        self.use_expr_y = False
        self._disp_x = None;
        self._disp_y = None
        # ★ 与 RichItem 一致的"叠加 FT"字段（在吸附结果上再偏移）
        self.custom_pos_expr = u""
        self.custom_pos_enabled = False
        self.custom_vo_expr = u""
        self.custom_vo_enabled = False
        self.custom_rot_expr = u""
        self.custom_rot_enabled = False

    def dx(self): return self._disp_x if self._disp_x is not None else self.x

    def dy(self): return self._disp_y if self._disp_y is not None else self.y

    def to_dict(self):
        return {"name": self.name, "x": self.x, "y": self.y,
                "visible": self.visible, "group_id": self.group_id,
                "bind_to": self.bind_to,
                "bind_dx": self.bind_dx, "bind_dy": self.bind_dy,
                "bind_angle": self.bind_angle,
                "bind_dx_expr": getattr(self, 'bind_dx_expr', u""),
                "bind_dy_expr": getattr(self, 'bind_dy_expr', u""),
                "bind_angle_expr": getattr(self, 'bind_angle_expr', u""),
                "expr_x": self.expr_x, "expr_y": self.expr_y,
                "use_expr_x": self.use_expr_x,
                "use_expr_y": self.use_expr_y,
                # ★ 叠加 FT 字段
                "custom_pos_expr": getattr(self, 'custom_pos_expr', u""),
                "custom_pos_enabled": getattr(self, 'custom_pos_enabled', False),
                "custom_vo_expr": getattr(self, 'custom_vo_expr', u""),
                "custom_vo_enabled": getattr(self, 'custom_vo_enabled', False),
                "custom_rot_expr": getattr(self, 'custom_rot_expr', u""),
                "custom_rot_enabled": getattr(self, 'custom_rot_enabled', False),
                # ★ 吸附对话框元信息
                **_helper_bind_dialog_dict(self)}

    @staticmethod
    def from_dict(d):
        p = HelperPoint(d.get("x", 0.0), d.get("y", 0.0),
                        name=d.get("name", u""))
        p.visible = bool(d.get("visible", True))
        p.group_id = d.get("group_id", None)
        p.bind_to = d.get("bind_to", u"")
        p.bind_dx = float(d.get("bind_dx", 0.0))
        p.bind_dy = float(d.get("bind_dy", 0.0))
        p.bind_angle = float(d.get("bind_angle", 0.0))
        p.bind_dx_expr = d.get("bind_dx_expr", u"")
        p.bind_dy_expr = d.get("bind_dy_expr", u"")
        p.bind_angle_expr = d.get("bind_angle_expr", u"")
        p.expr_x = d.get("expr_x", u"");
        p.expr_y = d.get("expr_y", u"")
        p.use_expr_x = bool(d.get("use_expr_x", False))
        p.use_expr_y = bool(d.get("use_expr_y", False))
        # ★ 叠加 FT 字段
        p.custom_pos_expr = d.get("custom_pos_expr", u"")
        p.custom_pos_enabled = bool(d.get("custom_pos_enabled", False))
        p.custom_vo_expr = d.get("custom_vo_expr", u"")
        p.custom_vo_enabled = bool(d.get("custom_vo_enabled", False))
        p.custom_rot_expr = d.get("custom_rot_expr", u"")
        p.custom_rot_enabled = bool(d.get("custom_rot_enabled", False))
        # ★ 恢复吸附对话框元信息
        _helper_restore_bind_dialog(p, d)
        return p


class HelperLine(object):
    def __init__(self, x1=0.0, y1=0.0, x2=0.0, y2=0.0, name=u""):
        self.name = name
        self.x1 = x1;
        self.y1 = y1
        self.x2 = x2;
        self.y2 = y2
        self.visible = True
        self.group_id = None
        self.bind_to = u""
        self.bind_dx = 0.0;
        self.bind_dy = 0.0;
        self.bind_angle = 0.0
        self.expr_x1 = u"";
        self.expr_y1 = u""
        self.expr_x2 = u"";
        self.expr_y2 = u""
        self.use_expr_x1 = False;
        self.use_expr_y1 = False
        self.use_expr_x2 = False;
        self.use_expr_y2 = False
        self._disp_x1 = None;
        self._disp_y1 = None
        self._disp_x2 = None;
        self._disp_y2 = None
        # ★ 叠加 FT 字段
        self.custom_pos_expr = u""
        self.custom_pos_enabled = False
        self.custom_vo_expr = u""
        self.custom_vo_enabled = False
        self.custom_rot_expr = u""
        self.custom_rot_enabled = False

    def dx1(self): return self._disp_x1 if self._disp_x1 is not None else self.x1

    def dy1(self): return self._disp_y1 if self._disp_y1 is not None else self.y1

    def dx2(self): return self._disp_x2 if self._disp_x2 is not None else self.x2

    def dy2(self): return self._disp_y2 if self._disp_y2 is not None else self.y2

    def to_dict(self):
        return {"name": self.name,
                "x1": self.x1, "y1": self.y1,
                "x2": self.x2, "y2": self.y2,
                "visible": self.visible, "group_id": self.group_id,
                "bind_to": self.bind_to,
                "bind_dx": self.bind_dx, "bind_dy": self.bind_dy,
                "bind_angle": self.bind_angle,
                "bind_dx_expr": getattr(self, 'bind_dx_expr', u""),
                "bind_dy_expr": getattr(self, 'bind_dy_expr', u""),
                "bind_angle_expr": getattr(self, 'bind_angle_expr', u""),
                "expr_x1": self.expr_x1, "expr_y1": self.expr_y1,
                "expr_x2": self.expr_x2, "expr_y2": self.expr_y2,
                "use_expr_x1": self.use_expr_x1,
                "use_expr_y1": self.use_expr_y1,
                "use_expr_x2": self.use_expr_x2,
                "use_expr_y2": self.use_expr_y2,
                # ★ 叠加 FT 字段
                "custom_pos_expr": getattr(self, 'custom_pos_expr', u""),
                "custom_pos_enabled": getattr(self, 'custom_pos_enabled', False),
                "custom_vo_expr": getattr(self, 'custom_vo_expr', u""),
                "custom_vo_enabled": getattr(self, 'custom_vo_enabled', False),
                "custom_rot_expr": getattr(self, 'custom_rot_expr', u""),
                "custom_rot_enabled": getattr(self, 'custom_rot_enabled', False),
                # ★ 吸附对话框元信息
                **_helper_bind_dialog_dict(self)}

    @staticmethod
    def from_dict(d):
        ln = HelperLine(d.get("x1", 0.0), d.get("y1", 0.0),
                        d.get("x2", 0.0), d.get("y2", 0.0),
                        name=d.get("name", u""))
        ln.visible = bool(d.get("visible", True))
        ln.group_id = d.get("group_id", None)
        ln.bind_to = d.get("bind_to", u"")
        ln.bind_dx = float(d.get("bind_dx", 0.0))
        ln.bind_dy = float(d.get("bind_dy", 0.0))
        ln.bind_angle = float(d.get("bind_angle", 0.0))
        ln.bind_dx_expr = d.get("bind_dx_expr", u"")
        ln.bind_dy_expr = d.get("bind_dy_expr", u"")
        ln.bind_angle_expr = d.get("bind_angle_expr", u"")
        ln.expr_x1 = d.get("expr_x1", u"");
        ln.expr_y1 = d.get("expr_y1", u"")
        ln.expr_x2 = d.get("expr_x2", u"");
        ln.expr_y2 = d.get("expr_y2", u"")
        ln.use_expr_x1 = bool(d.get("use_expr_x1", False))
        ln.use_expr_y1 = bool(d.get("use_expr_y1", False))
        ln.use_expr_x2 = bool(d.get("use_expr_x2", False))
        ln.use_expr_y2 = bool(d.get("use_expr_y2", False))
        # ★ 叠加 FT 字段
        ln.custom_pos_expr = d.get("custom_pos_expr", u"")
        ln.custom_pos_enabled = bool(d.get("custom_pos_enabled", False))
        ln.custom_vo_expr = d.get("custom_vo_expr", u"")
        ln.custom_vo_enabled = bool(d.get("custom_vo_enabled", False))
        ln.custom_rot_expr = d.get("custom_rot_expr", u"")
        ln.custom_rot_enabled = bool(d.get("custom_rot_enabled", False))
        # ★ 恢复吸附对话框元信息
        _helper_restore_bind_dialog(ln, d)
        return ln


class HelperCircle(object):
    def __init__(self, point=None, radius=0.3, name=u""):
        self.name = name
        self.point = point
        self.radius = radius
        self.visible = True
        self.group_id = None
        self.bind_to = u""
        self.bind_dx = 0.0;
        self.bind_dy = 0.0;
        self.bind_angle = 0.0
        self.expr_r = u""
        self.use_expr_r = False
        self._disp_r = None
        # ★ 叠加 FT 字段（作用在圆心）
        self.custom_pos_expr = u""
        self.custom_pos_enabled = False
        self.custom_vo_expr = u""
        self.custom_vo_enabled = False
        self.custom_rot_expr = u""
        self.custom_rot_enabled = False

    def dr(self): return self._disp_r if self._disp_r is not None else self.radius

    def to_dict(self, point_index=-1):
        return {"name": self.name, "radius": self.radius,
                "point_index": int(point_index),
                "visible": self.visible, "group_id": self.group_id,
                "bind_to": self.bind_to,
                "bind_dx": self.bind_dx, "bind_dy": self.bind_dy,
                "bind_angle": self.bind_angle,
                "bind_dx_expr": getattr(self, 'bind_dx_expr', u""),
                "bind_dy_expr": getattr(self, 'bind_dy_expr', u""),
                "bind_angle_expr": getattr(self, 'bind_angle_expr', u""),
                "expr_r": self.expr_r, "use_expr_r": self.use_expr_r,
                # ★ 叠加 FT 字段
                "custom_pos_expr": getattr(self, 'custom_pos_expr', u""),
                "custom_pos_enabled": getattr(self, 'custom_pos_enabled', False),
                "custom_vo_expr": getattr(self, 'custom_vo_expr', u""),
                "custom_vo_enabled": getattr(self, 'custom_vo_enabled', False),
                "custom_rot_expr": getattr(self, 'custom_rot_expr', u""),
                "custom_rot_enabled": getattr(self, 'custom_rot_enabled', False),
                # ★ 吸附对话框元信息
                **_helper_bind_dialog_dict(self)}

    @staticmethod
    def from_dict(d, point):
        c = HelperCircle(point, float(d.get("radius", 0.3)),
                         name=d.get("name", u""))
        c.visible = bool(d.get("visible", True))
        c.group_id = d.get("group_id", None)
        c.bind_to = d.get("bind_to", u"")
        c.bind_dx = float(d.get("bind_dx", 0.0))
        c.bind_dy = float(d.get("bind_dy", 0.0))
        c.bind_angle = float(d.get("bind_angle", 0.0))
        c.bind_dx_expr = d.get("bind_dx_expr", u"")
        c.bind_dy_expr = d.get("bind_dy_expr", u"")
        c.bind_angle_expr = d.get("bind_angle_expr", u"")
        c.expr_r = d.get("expr_r", u"")
        c.use_expr_r = bool(d.get("use_expr_r", False))
        # ★ 叠加 FT 字段
        c.custom_pos_expr = d.get("custom_pos_expr", u"")
        c.custom_pos_enabled = bool(d.get("custom_pos_enabled", False))
        c.custom_vo_expr = d.get("custom_vo_expr", u"")
        c.custom_vo_enabled = bool(d.get("custom_vo_enabled", False))
        c.custom_rot_expr = d.get("custom_rot_expr", u"")
        c.custom_rot_enabled = bool(d.get("custom_rot_enabled", False))
        # ★ 恢复吸附对话框元信息
        _helper_restore_bind_dialog(c, d)
        return c


def _encode_helpers(points, lines, circles):
    """把所有辅助对象编码成 list；圆带 point_index 引用"""
    idx_map = {id(p): i for i, p in enumerate(points)}
    out = []
    for p in points:
        d = p.to_dict();
        d["type"] = "point";
        out.append(d)
    for ln in lines:
        d = ln.to_dict();
        d["type"] = "line";
        out.append(d)
    for c in circles:
        d = c.to_dict(idx_map.get(id(c.point), -1))
        d["type"] = "circle";
        out.append(d)
    return out


def _decode_helpers(data):
    """从 list 恢复 (points, lines, circles)"""
    if not data: return [], [], []
    points = [];
    lines = [];
    circles = []
    for d in data:
        if d.get("type") == "point":
            points.append(HelperPoint.from_dict(d))
    for d in data:
        t = d.get("type")
        if t == "line":
            lines.append(HelperLine.from_dict(d))
        elif t == "circle":
            pi = int(d.get("point_index", -1))
            p = points[pi] if 0 <= pi < len(points) else None
            if p is None:
                p = HelperPoint();
                points.append(p)
            circles.append(HelperCircle.from_dict(d, p))
    return points, lines, circles


# ================================================================ 数据模型
class RichItem(object):
    def __init__(self, text=u"○", x=0.0, y=0.0, size=None):
        self.text = text
        self.name = u""
        self.bind_to = u""
        self.bind_dx = 0.0
        self.bind_dy = 0.0
        self.bind_angle = 0.0
        self.bind_dx_expr = u""
        self.bind_dy_expr = u""
        self.bind_angle_expr = u""
        self.x = float(x);
        self.y = float(y)
        self.size = float(size) if size is not None else DEFAULT_GLOBAL_SIZE
        self.size_is_custom = False
        self.rotation = 0.0
        self.color = QColor(DEFAULT_COLOR)
        self.bold = False;
        self.italic = False
        self.underline = False;
        self.strike = False
        self.hidden = False
        self.custom_pos_expr = ""
        self.custom_pos_enabled = False
        self.custom_vo_expr = ""
        self.custom_vo_enabled = False
        self.custom_size_expr = ""
        self.custom_size_enabled = False
        self.custom_rot_expr = ""
        self.custom_rot_enabled = False
        self.compensate_offset = False
        self._expr_state = ExprState()
        self._display_cache = text
        self._disp_size = None
        self._disp_x = None
        self._disp_y = None
        self._disp_rot = None
        # 表达式覆盖画布显示（由 Run Test 开启时计算）
        self._disp_size = None
        self._disp_x = None
        self._disp_y = None
        self._disp_rot = None

    def make_font(self, px, bold=None, italic=None):
        f = QFont(DEFAULT_FONT_FAMILY)
        f.setPixelSize(max(1, int(round(px))))
        f.setBold(bool(self.bold) if bold is None else bool(bold))
        f.setItalic(bool(self.italic) if italic is None else bool(italic))
        return f

    def _glyph_key(self):
        """取字形矫正表用的 key：
        · 无标签 → 直接用 text
        · 有标签 → 剥掉所有 <...>，返回纯文本部分
        这样 <alpha=#80>■</alpha> 和 ■ 走同一套矫正。
        """
        t = self.text or u""
        if '<' not in t:
            return t
        try:
            return re.sub(r'<[^>]+>', u'', t)
        except Exception:
            return t

    def _auto_close_tags(self):
        """根据 self.text 里未闭合的 <mark> / <alpha> 补上关闭标签"""
        t = self.text or u""
        parts = []
        if _unclosed_count(t, 'mark') > 0:
            parts.append(u'</mark>')
        if _unclosed_count(t, 'alpha') > 0:
            parts.append(u'<alpha=#FF>')
        return u''.join(parts)

    def eval_display(self, variables, dt, use_expr=False):
        if not has_expr(self.text):
            self._display_cache = self.text
        else:
            self._display_cache = eval_text_stateful(
                self.text, variables, dt, self._expr_state, id(self))
        if use_expr:
            def _ev(expr, salt):
                s = expr.strip()
                if not s: return None
                if not (s.startswith('{') and s.endswith('}')):
                    s = '{' + s + '}'
                r = eval_text_stateful(s, variables, dt,
                                       self._expr_state, id(self) + salt)
                try:
                    return float(r)
                except Exception:
                    return None

            # ★ fx 勾选 且 函数栏非空 → 用函数；否则 None（画布用数值框）
            if self.custom_size_enabled and self.custom_size_expr.strip():
                self._disp_size = _ev(self.custom_size_expr, 1000)
            else:
                self._disp_size = None
            if self.custom_pos_enabled and self.custom_pos_expr.strip():
                v = _ev(self.custom_pos_expr, 2000)
                self._disp_x = (v / POS_PER_WORLD) if v is not None else None
            else:
                self._disp_x = None
            if self.custom_vo_enabled and self.custom_vo_expr.strip():
                v = _ev(self.custom_vo_expr, 3000)
                self._disp_y = (-v / VO_PER_WORLD) if v is not None else None
            else:
                self._disp_y = None
            if self.custom_rot_enabled and self.custom_rot_expr.strip():
                self._disp_rot = _ev(self.custom_rot_expr, 4000)
            else:
                self._disp_rot = None
        else:
            self._disp_size = None
            self._disp_x = None
            self._disp_y = None
            self._disp_rot = None

    def display_text(self):
        return self._display_cache if self._display_cache is not None else self.text

    def disp_size(self):
        base = self._disp_size if self._disp_size is not None else self.size
        key = self._glyph_key()
        info = GLYPH_CORRECTIONS.get(key)
        if info is not None and "disp_scale" in info:
            return base * info["disp_scale"]
        if _is_symbol_text(key):
            return base
        return base * PLAIN_DRAW_SCALE

    def disp_center(self):
        x = self._disp_x if self._disp_x is not None else self.x
        y = self._disp_y if self._disp_y is not None else self.y
        return (x, y)

    def disp_rotation(self):
        return self._disp_rot if self._disp_rot is not None else self.rotation

    def disp_up_world(self, canvas_h=2.0):
        # ★ size 用函数 + 未开补偿 → 画布不做字形上抬
        size_uses_expr = bool(self.custom_size_enabled
                              and self.custom_size_expr.strip())
        if size_uses_expr and not self.compensate_offset:
            return 0.0
        # 原有逻辑
        eff = self.disp_size()
        key = self._glyph_key()
        info = GLYPH_CORRECTIONS.get(key)
        if info is not None and "disp_up_vo_fn" in info:
            return info["disp_up_vo_fn"](eff) / VO_PER_WORLD
        if _is_symbol_text(key):
            return get_canvas_up_world(key, self.size)
        up_vo = PLAIN_DRAW_UP_VO_PER_SIZE * eff
        return up_vo / VO_PER_WORLD

    def disp_pos_world(self, canvas_w=1.0):
        eff = self.disp_size()
        key = self._glyph_key()
        info = GLYPH_CORRECTIONS.get(key)
        if info is not None and "disp_pos_fn" in info:
            return info["disp_pos_fn"](eff) / POS_PER_WORLD
        return 0.0

    def to_rich(self, cw, ch, gs, gr):
        # 辅助对象引用由调用方（items_to_rich）预先展开
        size_uses_expr = bool(self.custom_size_enabled
                              and self.custom_size_expr.strip())
        pos_uses_expr = bool(self.custom_pos_enabled
                             and self.custom_pos_expr.strip())
        vo_uses_expr = bool(self.custom_vo_enabled
                            and self.custom_vo_expr.strip())

        # ---- pos ----
        if pos_uses_expr:
            pos_field = _wrap_expr(self.custom_pos_expr)
        else:
            pos_field = _fmt(self.x * POS_PER_WORLD)

        # ---- voffset ----
        if vo_uses_expr:
            vo_field = _wrap_expr(self.custom_vo_expr)
        else:
            vo_field = _fmt(-self.y * VO_PER_WORLD)

        # ---- size ----
        if size_uses_expr:
            size_field = _wrap_expr(self.custom_size_expr)
        else:
            size_field = _fmt(self.size)

        # ---- rotate ----
        rot_field = None
        if self.custom_rot_enabled and self.custom_rot_expr.strip():
            rot_field = _wrap_expr(self.custom_rot_expr)
        elif abs(self.rotation) > 1e-3:
            rot_field = _fmt(self.rotation)

        # ---- 补偿偏移 ----
        # size 用数值栏 → 无条件加（补偿为常量，直接算进数字）
        # size 用函数栏 → 只有开关打开才加（写成 {xxx} 表达式）
        need_comp = (not size_uses_expr) or self.compensate_offset

        if need_comp:
            g_str = _fmt(gs)
            size_inner = (_unwrap_expr(self.custom_size_expr)
                          if size_uses_expr else _fmt(self.size))
            info = GLYPH_CORRECTIONS.get(self.text)
            if info is not None:
                # ★ 未显式指定 out_vo_str / out_pos_str 的字符，
                #   回落到默认公式（避免因为进入了 GLYPH_CORRECTIONS
                #   就丢掉输出补偿）
                vo_comp_tpl = info.get("out_vo_str") or u"0.345*({G}-({C}))"
                pos_comp_tpl = info.get("out_pos_str")
            else:
                vo_comp_tpl = u"0.345*({G}-({C}))"
                pos_comp_tpl = None

            def _resolve_tpl(tpl):
                s = tpl.replace("{C}", size_inner).replace("{G}", g_str)
                if not size_uses_expr:
                    try:
                        return float(eval(s, {"__builtins__": {}}, {})), None
                    except Exception:
                        return None, s
                return None, s

            def _add_comp(field, uses_expr, tpl):
                if tpl is None:
                    return field
                val, expr = _resolve_tpl(tpl)
                if val is not None:
                    # 数值补偿
                    if uses_expr:
                        return _add_to_expr(field, _fmt(val))
                    try:
                        base = float(_unwrap_expr(field))
                    except Exception:
                        base = 0.0
                    return _fmt(base + val)
                else:
                    return _add_to_expr(field, expr)

            vo_field = _add_comp(vo_field, vo_uses_expr, vo_comp_tpl)
            pos_field = _add_comp(pos_field, pos_uses_expr, pos_comp_tpl)

        out = [u"<voffset=%s><pos=%s><size=%s>" % (
            vo_field, pos_field, size_field)]
        closes = []
        if rot_field is not None:
            out.append(u"<rotate=%s>" % rot_field)
            closes.append(u"</rotate>")
        if self.color != DEFAULT_COLOR:
            c = self.color
            out.append(u"<color=#%02X%02X%02X>" % (c.red(), c.green(), c.blue()))
            closes.append(u"</color>")
        if self.underline: out.append(u"<u>")
        if self.strike: out.append(u"<s>")
        out.append(self.text)
        # ★ 自动补上未闭合的 </mark> / </alpha>，避免影响后续输出
        auto_close = self._auto_close_tags()
        if auto_close:
            out.append(auto_close)
        if self.strike: out.append(u"</s>")
        if self.underline: out.append(u"</u>")
        for c in reversed(closes): out.append(c)
        out.append(u"</size></pos></voffset>")
        return u"".join(out)

    def to_dict(self):
        return {"text": self.text, "name": self.name,
                "bind_to": self.bind_to,
                "bind_dx": self.bind_dx, "bind_dy": self.bind_dy,
                "bind_angle": self.bind_angle,
                "bind_dx_expr": self.bind_dx_expr,
                "bind_dy_expr": self.bind_dy_expr,
                "bind_angle_expr": self.bind_angle_expr,
                "bind_dialog_mode": getattr(self, '_bind_dialog_mode', None),
                "bind_dialog_ctrl": getattr(self, '_bind_dialog_ctrl', None),
                "bind_dialog_t0": getattr(self, '_bind_dialog_t0', None),
                "bind_dialog_t1": getattr(self, '_bind_dialog_t1', None),
                "bind_dialog_tangent": getattr(self, '_bind_dialog_tangent', None),
                "bind_dialog_reverse": getattr(self, '_bind_dialog_reverse', None),
                "bind_dialog_start_angle": getattr(self, '_bind_dialog_start_angle', None),
                "bind_dialog_obj_offset": getattr(self, '_bind_dialog_obj_offset', None),
                "x": self.x, "y": self.y,
                "size": self.size, "size_is_custom": self.size_is_custom,
                "rotation": self.rotation, "color": self.color.name(),
                "bold": self.bold, "italic": self.italic,
                "underline": self.underline, "strike": self.strike,
                "hidden": self.hidden,
                "custom_pos_expr": self.custom_pos_expr,
                "custom_pos_enabled": self.custom_pos_enabled,
                "custom_vo_expr": self.custom_vo_expr,
                "custom_vo_enabled": self.custom_vo_enabled,
                "custom_size_expr": self.custom_size_expr,
                "custom_size_enabled": self.custom_size_enabled,
                "custom_rot_expr": self.custom_rot_expr,
                "custom_rot_enabled": self.custom_rot_enabled,
                "compensate_offset": self.compensate_offset}

    @staticmethod
    def from_dict(d):
        it = RichItem(d.get("text", u""), d.get("x", 0), d.get("y", 0),
                      size=float(d.get("size", DEFAULT_GLOBAL_SIZE)))
        it.name = d.get("name", u"")
        it.bind_to = d.get("bind_to", u"")
        it.bind_dx = float(d.get("bind_dx", 0.0))
        it.bind_dy = float(d.get("bind_dy", 0.0))
        it.bind_angle = float(d.get("bind_angle", 0.0))
        it.bind_dx_expr = d.get("bind_dx_expr", u"")
        it.bind_dy_expr = d.get("bind_dy_expr", u"")
        it.bind_angle_expr = d.get("bind_angle_expr", u"")
        it.size_is_custom = bool(d.get("size_is_custom", False))
        it.rotation = float(d.get("rotation", 0))
        it.color = QColor(d.get("color", "#000000"))
        it.bold = bool(d.get("bold", False))
        it.italic = bool(d.get("italic", False))
        it.underline = bool(d.get("underline", False))
        it.strike = bool(d.get("strike", False))
        it.hidden = bool(d.get("hidden", False))
        it.custom_pos_expr = d.get("custom_pos_expr", "")
        it.custom_pos_enabled = bool(d.get("custom_pos_enabled", False))
        it.custom_vo_expr = d.get("custom_vo_expr", "")
        it.custom_vo_enabled = bool(d.get("custom_vo_enabled", False))
        it.custom_size_expr = d.get("custom_size_expr", "")
        it.custom_size_enabled = bool(d.get("custom_size_enabled", False))
        it.custom_rot_expr = d.get("custom_rot_expr", "")
        it.custom_rot_enabled = bool(d.get("custom_rot_enabled", False))
        it.compensate_offset = bool(d.get("compensate_offset", False))
        try:
            if d.get("bind_dialog_mode") is not None:
                it._bind_dialog_mode = d["bind_dialog_mode"]
            if d.get("bind_dialog_ctrl") is not None:
                it._bind_dialog_ctrl = d["bind_dialog_ctrl"]
            if d.get("bind_dialog_t0") is not None:
                it._bind_dialog_t0 = float(d["bind_dialog_t0"])
            if d.get("bind_dialog_t1") is not None:
                it._bind_dialog_t1 = float(d["bind_dialog_t1"])
            if d.get("bind_dialog_tangent") is not None:
                it._bind_dialog_tangent = bool(d["bind_dialog_tangent"])
            if d.get("bind_dialog_reverse") is not None:
                it._bind_dialog_reverse = bool(d["bind_dialog_reverse"])
            if d.get("bind_dialog_start_angle") is not None:
                it._bind_dialog_start_angle = float(d["bind_dialog_start_angle"])
            if d.get("bind_dialog_obj_offset") is not None:
                it._bind_dialog_obj_offset = float(d["bind_dialog_obj_offset"])
        except Exception:
            pass
        return it


def items_to_rich(items, cw, ch, gs, gr, resolve=None):
    lines = [OUT_PREFIX]
    for it in items:
        if resolve is not None:
            saved = (it.custom_pos_expr, it.custom_vo_expr,
                     it.custom_size_expr, it.custom_rot_expr)
            try:
                it.custom_pos_expr = resolve(saved[0])
                it.custom_vo_expr = resolve(saved[1])
                it.custom_size_expr = resolve(saved[2])
                it.custom_rot_expr = resolve(saved[3])
                lines.append(it.to_rich(cw, ch, gs, gr))
            finally:
                (it.custom_pos_expr, it.custom_vo_expr,
                 it.custom_size_expr, it.custom_rot_expr) = saved
        else:
            lines.append(it.to_rich(cw, ch, gs, gr))
    lines.append(OUT_SUFFIX)
    return u"\n".join(lines)


RE_LINE = re.compile(
    r"^<voffset=([^>]+)><pos=([^>]+)><size=([^>]+)>(.*)</size></pos></voffset>$")
RE_ROT = re.compile(r"<rotate=(-?[\d.]+)>")
RE_COL = re.compile(r"<color=#([0-9A-Fa-f]{6})>")


def parse_rich_string(s, cw, ch, gs, gr):
    """解析输入的富文本字符串。

    · 先尝试按本工具导出的标准格式（每行
      <voffset=..><pos=..><size=..>..</size></pos></voffset>）逐行解析
    · 如果一行都没匹配到，则把整段当作一个"字符对象"导入，
      文本内容原样保留（画布会按 TMP 富文本 + 表达式渲染）
    """
    items = []
    for raw in s.split("\n"):
        line = raw.strip()
        if not line: continue
        m = RE_LINE.match(line)
        if not m: continue
        vo_s = m.group(1)
        pos_s = m.group(2)
        eff_s = m.group(3)
        rest = m.group(4)
        try:
            vo = float(vo_s)
            pos = float(pos_s)
            eff = float(eff_s)
        except Exception:
            continue
        rot = 0.0
        rm = RE_ROT.search(rest)
        if rm: rot = float(rm.group(1))
        color = QColor(DEFAULT_COLOR)
        cm = RE_COL.search(rest)
        if cm: color = QColor(u"#" + cm.group(1))
        bold = u"<b>" in rest
        italic = u"<i>" in rest
        text = re.sub(r"<[^>]+>", u"", rest).strip()
        if not text: continue
        vo_corr = get_out_vo(text, eff, gs, ch, gr)
        vo_base = vo - vo_corr
        it = RichItem(text, size=eff)
        it.x = pos / POS_PER_WORLD
        it.y = -vo_base / VO_PER_WORLD
        it.rotation = rot
        it.color = color
        it.bold = bold
        it.italic = italic
        it.size_is_custom = True
        items.append(it)

    # ★ 未匹配到任何标准行 → 整段作为单个字符对象导入
    if not items:
        whole = (s or u"").strip()
        if whole:
            it = RichItem(whole, 0.0, 0.0, size=DEFAULT_GLOBAL_SIZE)
            it.size_is_custom = False
            items.append(it)
    return items


# ---------------------------------------------------------------- 符号表
SYMBOLS = [u"●", u"○", u"I", u"■", u"▲",
           u"↑", u"↓", u"←", u"→"]
# ★ 菜单项：(显示标签, 实际文本, 旋转角度)
SYMBOL_MENU_ITEMS = [
    (u"●", u"●", 0.0),
    (u"○", u"○", 0.0),
    (u"I", u"I", 0.0),  # 竖线
    (u"—", u"I", 90.0),  # 横线（I 旋转 90°，输出自带 rotate=90）
    (u"■", u"■", 0.0),
    (u"▲", u"▲", 0.0),
    (u"↑", u"↑", 0.0),
    (u"↓", u"↓", 0.0),
    (u"←", u"←", 0.0),
    (u"→", u"→", 0.0),
]
SYMBOL_SET = set(SYMBOLS) | set(GLYPH_CORRECTIONS.keys())
FORCE_PLAIN_TEXT = {u"I"}


def _is_symbol_text(text):
    if not text or len(text) != 1: return False
    if text in FORCE_PLAIN_TEXT: return False
    return text in SYMBOL_SET


def _fmt(v):
    try:
        if not _math.isfinite(v):
            return u"0"
    except Exception:
        pass
    if abs(v - round(v)) < 1e-3: return u"%d" % int(round(v))
    s = u"%.5f" % v
    if u'.' in s: s = s.rstrip(u'0').rstrip(u'.')
    return s


def _unclosed_count(text, tag):
    """返回 text 里"未关闭"的 <tag> 数量。

    · mark：靠 <mark=...> 与 </mark> 配对计数
    · alpha：不是配对标签，用 <alpha=#XX> 切换；
      找最后一个 <alpha=#XX>，值 < #FF 视为"未关闭"（1），
      否则视为已关闭（0）
    """
    if not text:
        return 0
    try:
        if tag == 'alpha':
            matches = re.findall(r'<alpha=\s*#?([0-9A-Fa-f]+)>', text)
            if not matches:
                return 0
            last = matches[-1]
            try:
                v = int(last[:2], 16)
            except Exception:
                v = 0xFF
            return 0 if v >= 0xFF else 1
        open_re = re.compile(r'<' + re.escape(tag) + r'(?:\s*=[^>]*)?>')
        close_re = re.compile(r'</' + re.escape(tag) + r'\s*>')
        return max(0, len(open_re.findall(text)) -
                   len(close_re.findall(text)))
    except Exception:
        return 0


# ================================================================
#                       精度控件
# ================================================================
class CanvasSizeSpin(QDoubleSpinBox):
    """画布 W/H：显示 2 位、可输 4 位、步进 0.01"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDecimals(4)
        self.setKeyboardTracking(False)
        self.setSingleStep(0.01)
        self.setRange(0.1, 20.0)

    def textFromValue(self, v):
        v2 = round(v, 2)
        if abs(v - v2) < 1e-9:
            return ('%.2f' % v2)
        return ('%.4f' % v)


class VTOLTrimSpin(QDoubleSpinBox):
    """VTOL/Trim：显示 2 位、可输 4 位、步进 0.01"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDecimals(4)
        self.setKeyboardTracking(False)
        self.setSingleStep(0.01)
        self.setRange(-1.0, 1.0)

    def textFromValue(self, v):
        v2 = round(v, 2)
        if abs(v - v2) < 1e-9:
            return ('%.2f' % v2)
        return ('%.4f' % v)


class SpacingSpin(QDoubleSpinBox):
    """网格间距：默认显示 2 位；手动输入超过 2 位则按实际位数显示
    ★ 显示值 = 内部值 / 10
      （用户看到的数字是原来的 1/10；内部值 snap_spacing 保持不变，
        网格实际步长完全不变）
    ★ 滚轮 / 步进 = 0.01（显示单位）
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # ★ decimals 放大到 5，避免用户输入的 3~5 位小数被截断
        #   （默认显示仍是 2 位，见 textFromValue）
        self.setDecimals(5)
        self.setKeyboardTracking(False)
        # ★ 显示单位步长 0.01 → 内部值步长 0.1
        self.setSingleStep(0.1)
        # ★ 内部值范围 [0.1, 100.0]，对应显示值 [0.01, 10.0]
        #   最小值 0.01 → 滚轮降到 0.01 就到底，不再变
        self.setRange(0.1, 100.0)

    def textFromValue(self, v):
        disp = v / 10.0
        # 刚好是 2 位小数以内 → 显示 2 位
        r2 = round(disp, 2)
        if abs(disp - r2) < 1e-9:
            return ('%.2f' % r2)
        # 否则按实际值显示（最多 5 位，去掉尾随 0）
        s = ('%.5f' % disp)
        if '.' in s:
            s = s.rstrip('0').rstrip('.')
        return s

    def valueFromText(self, text):
        # 输入值 × 10 转成内部值
        try:
            return float(text) * 10.0
        except Exception:
            return 0.0

    def validate(self, text, pos):
        """强制用 C locale 解析，避免中文 / 其它 locale 下
        小数点解析差异导致输入被拒绝"""
        t = (text or u"").strip()
        if t in (u"", u"-", u".", u"-."):
            return QValidator.Intermediate, text, pos
        try:
            v = float(t)
        except Exception:
            return QValidator.Invalid, text, pos
        if v < 0:
            return QValidator.Invalid, text, pos
        # v 是显示值，内部值 = v * 10；只要内部值不超过 range 上限即可
        if v * 10.0 > self.maximum():
            return QValidator.Intermediate, text, pos
        return QValidator.Acceptable, text, pos


_SIZE_TEXT_RE = re.compile(r'^-?\d*\.?\d*%?$')
_POS_TEXT_RE = re.compile(r'^-?\d*\.?\d*$')


class PosVOSpinBox(QDoubleSpinBox):
    """pos / voffset / rotate 输入框：
    · 允许输入任意小数位（如 1.23456789）
    · 回车 / 失焦后 Qt 自动按 decimals=5 四舍五入显示
    · 自动剥离 suffix / prefix（rotate 带 " °" 后缀）
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDecimals(5)
        self.setKeyboardTracking(False)
        self.setSingleStep(0.5)

    def _clean(self, text):
        t = text or u""
        suf = self.suffix()
        if suf and t.endswith(suf):
            t = t[:-len(suf)]
        pre = self.prefix()
        if pre and t.startswith(pre):
            t = t[len(pre):]
        return t.strip()

    def validate(self, text, pos):
        t = self._clean(text)
        if not _POS_TEXT_RE.match(t):
            return QValidator.Invalid, text, pos
        if t in (u'', u'-', u'.', u'-.'):
            return QValidator.Intermediate, text, pos
        try:
            float(t)
            return QValidator.Acceptable, text, pos
        except Exception:
            return QValidator.Intermediate, text, pos

    def valueFromText(self, text):
        t = self._clean(text)
        try:
            return float(t)
        except Exception:
            return 0.0


class SizeSpinBox(QDoubleSpinBox):
    """size 输入框：允许输入 "35%" 或 "0.35"。
    · 输入带 % 时按百分比解析（35% → 0.35）
    · 输入不带 % 时按普通数字
    · 确认 / 失焦后统一显示为小数
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(-9999.0, 9999.0)
        self.setDecimals(5)
        self.setKeyboardTracking(False)
        self.setSingleStep(0.5)
        self.setFixedWidth(78)

    def validate(self, text, pos):
        t = text or u""
        if not _SIZE_TEXT_RE.match(t):
            return QValidator.Invalid, text, pos
        stripped = t.rstrip('%')
        if stripped in (u'', u'-', u'.', u'-.'):
            return QValidator.Intermediate, text, pos
        try:
            float(stripped)
            return QValidator.Acceptable, text, pos
        except Exception:
            return QValidator.Intermediate, text, pos

    def valueFromText(self, text):
        t = (text or u"").strip()
        if t.endswith('%'):
            try:
                return float(t[:-1]) / 100.0
            except Exception:
                pass
        try:
            return float(t)
        except Exception:
            return 0.0


# ================================================================
#                       可展开函数输入框
# ================================================================
# ============================================================
#                  Tab 自动补全
# ============================================================
_GLOBAL_WORDS_HOOK = [None]


def set_global_words_provider(fn):
    """主窗口调用：注册"额外候选词"（比如自定义变量名）"""
    _GLOBAL_WORDS_HOOK[0] = fn


def _all_words():
    words = list(CONTROL_VARS) + list(FLIGHT_VARS)
    words += list(EXPR_FUNCS.keys())
    words += ['pi', 'e']
    try:
        hook = _GLOBAL_WORDS_HOOK[0]
        if hook is not None:
            words += list(hook() or [])
    except Exception:
        pass
    seen = set()
    out = []
    for w in words:
        if w and w not in seen:
            seen.add(w)
            out.append(w)
    return out


class _AutoCompleter(QObject):
    """给 QPlainTextEdit / QLineEdit 挂 Tab 补全"""

    def __init__(self, editor, words_provider, parent=None):
        super().__init__(parent or editor)
        self.editor = editor
        self.words_provider = words_provider
        self.popup = QListWidget()
        # ★ 用 Tool 而不是 Popup：Popup 会 grab 键盘，导致"卡住"
        self.popup.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.popup.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.popup.setFocusPolicy(Qt.NoFocus)
        self.popup.setStyleSheet(
            "QListWidget { background:#2a2d31; color:#e0e0e0;"
            " border:1px solid #555; font-family:Consolas; font-size:11px; }"
            "QListWidget::item { padding:2px 8px; }"
            "QListWidget::item:selected { background:#4a90d9; color:#ffffff; }")
        self.popup.hide()
        # ★ 鼠标点击也能确认
        self.popup.itemClicked.connect(self._on_item_clicked)
        editor.installEventFilter(self)

    def _on_item_clicked(self, item):
        if item is None:
            return
        self.popup.setCurrentItem(item)
        self._accept_current()

    def _is_plain(self):
        return isinstance(self.editor, QPlainTextEdit)

    def _get_prefix(self):
        try:
            if self._is_plain():
                pos = self.editor.textCursor().position()
                text = self.editor.toPlainText()
            else:
                pos = self.editor.cursorPosition()
                text = self.editor.text()
            i = pos
            while i > 0 and (text[i - 1].isalnum() or text[i - 1] == '_'):
                i -= 1
            return text[i:pos], i, pos
        except Exception:
            return '', 0, 0

    def _show_popup(self, prefix):
        try:
            words = self.words_provider() or []
        except Exception:
            words = []
        pl = prefix.lower()
        items = [w for w in words if w.lower().startswith(pl)]
        items.sort(key=lambda x: (len(x), x.lower()))
        if not items:
            self.popup.hide()
            return False
        self.popup.clear()
        for w in items[:20]:
            self.popup.addItem(w)
        self.popup.setCurrentRow(0)
        try:
            if self._is_plain():
                rect = self.editor.cursorRect()
                gp = self.editor.mapToGlobal(rect.bottomLeft())
            else:
                gp = self.editor.mapToGlobal(
                    QPoint(0, self.editor.height()))
            self.popup.move(gp)
            self.popup.setMinimumWidth(170)
            row_h = 20
            self.popup.setFixedHeight(min(len(items), 10) * row_h + 6)
            self.popup.show()
            self.popup.raise_()
        except Exception:
            pass
        return True

    def _accept_current(self):
        if not self.popup.isVisible():
            return False
        item = self.popup.currentItem()
        if item is None:
            return False
        word = item.text()
        _, start, end = self._get_prefix()
        try:
            if self._is_plain():
                cur = self.editor.textCursor()
                cur.setPosition(start)
                cur.setPosition(end, QTextCursor.KeepAnchor)
                cur.insertText(word)
                self.editor.setTextCursor(cur)
            else:
                txt = self.editor.text()
                new = txt[:start] + word + txt[end:]
                self.editor.setText(new)
                self.editor.setCursorPosition(start + len(word))
        except Exception:
            pass
        self.popup.hide()
        return True

    def _move(self, delta):
        if not self.popup.isVisible():
            return False
        n = self.popup.count()
        if n == 0:
            return False
        self.popup.setCurrentRow((self.popup.currentRow() + delta) % n)
        return True

    def _hide_popup(self):
        try:
            self.popup.hide()
        except Exception:
            pass

    def _auto_show(self):
        """延时弹候选（让编辑器先处理这次按键，再读新光标位置）"""
        try:
            prefix, _, _ = self._get_prefix()
            if len(prefix) < 1:
                self._hide_popup()
                return
            self._show_popup(prefix)
        except Exception:
            pass

    def eventFilter(self, obj, event):
        if obj is not self.editor:
            return False
        et = event.type()
        # 编辑器失焦 → 关闭候选
        if et == QEvent.FocusOut:
            self._hide_popup()
            return False
        if et != QEvent.KeyPress:
            return False
        k = event.key()
        mods = event.modifiers()

        # ---- 候选可见时：上下选择、Tab/Enter 确认、Esc 取消 ----
        if self.popup.isVisible():
            if k == Qt.Key_Up:
                self._move(-1)
                return True
            if k == Qt.Key_Down:
                self._move(1)
                return True
            if k in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab):
                self._accept_current()
                return True
            if k == Qt.Key_Escape:
                self._hide_popup()
                return True

        # ---- Tab：有前缀 → 弹或直接确认 ----
        if k == Qt.Key_Tab:
            prefix, _, _ = self._get_prefix()
            if prefix:
                if self.popup.isVisible():
                    self._accept_current()
                else:
                    self._show_popup(prefix)
                return True
            # 无前缀：走默认 Tab 行为
            return False

        # ---- 普通字符输入 / 退格：自动弹候选 ----
        is_char = (32 <= k < 127) and not (
            mods & (Qt.ControlModifier | Qt.AltModifier))
        is_back = (k == Qt.Key_Backspace)
        if is_char or is_back:
            # ★ 让编辑器先处理按键，再延时读取新前缀并弹候选
            QTimer.singleShot(0, self._auto_show)
            return False

        # ---- 其它按键（方向左右 / Home / End / Delete 等）→ 关闭候选 ----
        if self.popup.isVisible():
            self._hide_popup()
        return False


class FnLineEdit(QPlainTextEdit):
    """函数输入框：聚焦展开（约 5 行），失焦收起；自动换行"""

    def __init__(self, placeholder=u"", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self._h_collapsed = 26
        self._h_expanded = 110  # 约 5 行
        self.setFixedHeight(self._h_collapsed)
        self.setLineWrapMode(QPlainTextEdit.WidgetWidth)  # 自动换行
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTabChangesFocus(False)  # ★ 交给 _AutoCompleter 处理 Tab
        self._completer = _AutoCompleter(self, _all_words)

    def focusInEvent(self, e):
        self.setFixedHeight(self._h_expanded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        super().focusInEvent(e)

    def focusOutEvent(self, e):
        self.setFixedHeight(self._h_collapsed)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        super().focusOutEvent(e)


# ================================================================ 快速面板
class _SliderRow(QWidget):
    valueChanged = pyqtSignal(float)

    def __init__(self, label, lo, hi, decimals=3, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(20)
        h = QHBoxLayout(self);
        h.setContentsMargins(0, 0, 0, 0);
        h.setSpacing(4)
        lbl = QLabel(label);
        lbl.setFixedWidth(46)
        lbl.setMinimumHeight(18)
        lbl.setStyleSheet("color:#cccccc; font-size:11px;")
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(-10000, 10000)
        self.slider.setMinimumHeight(18)  # ★ 防止被压扁
        self.spin = QDoubleSpinBox()
        self.spin.setRange(lo, hi);
        self.spin.setDecimals(decimals)
        self.spin.setFixedWidth(72)
        self.spin.setMinimumHeight(18)  # ★ 防止被压扁
        self.spin.setButtonSymbols(QDoubleSpinBox.NoButtons)
        h.addWidget(lbl);
        h.addWidget(self.slider, 1);
        h.addWidget(self.spin)
        self._lo = lo;
        self._hi = hi
        self._updating = False
        # ★ 滚轮步长提供者（动态获取；None 表示用默认滚轮行为）
        self._wheel_step_provider = None
        self.slider.installEventFilter(self)
        self.spin.installEventFilter(self)
        self.slider.valueChanged.connect(self._on_slider)
        self.spin.valueChanged.connect(self._on_spin)

    def set_wheel_step_provider(self, fn):
        """设置滚轮步长提供者（返回 float 显示单位步长）"""
        self._wheel_step_provider = fn

    def eventFilter(self, obj, event):
        """滚轮在 spin / slider 上时，按 step 跳一格"""
        try:
            if (event.type() == QEvent.Wheel
                    and self._wheel_step_provider is not None
                    and (obj is self.slider or obj is self.spin)):
                try:
                    step = float(self._wheel_step_provider())
                except Exception:
                    step = 0.0
                if step <= 0:
                    return False
                d = event.angleDelta().y()
                if d == 0:
                    return False
                sign = 1.0 if d > 0 else -1.0
                if obj is self.spin:
                    v = self.spin.value() + sign * step
                    v = max(self._lo, min(self._hi, v))
                    self.spin.setValue(v)
                else:
                    rng = self._hi - self._lo
                    if rng <= 1e-9:
                        return True
                    step_px = max(1, int(round(step * 20000.0 / rng)))
                    v = self.slider.value() + int(sign * step_px)
                    v = max(-10000, min(10000, v))
                    self.slider.setValue(v)
                return True
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def _from_slider(self, v):
        return self._lo + (self._hi - self._lo) * (v + 10000) / 20000.0

    def _to_slider(self, v):
        v = max(self._lo, min(self._hi, float(v)))
        return int(round((v - self._lo) / (self._hi - self._lo) * 20000 - 10000))

    def _on_slider(self, v):
        if self._updating: return
        self._updating = True
        val = self._from_slider(v)
        self.spin.setValue(val)
        self._updating = False
        self.valueChanged.emit(val)

    def _on_spin(self, v):
        if self._updating: return
        self._updating = True
        self.slider.setValue(self._to_slider(v))
        self._updating = False
        self.valueChanged.emit(float(v))

    def set_value(self, v):
        self._updating = True
        v = max(self._lo, min(self._hi, float(v)))
        self.spin.setValue(v)
        self.slider.setValue(self._to_slider(v))
        self._updating = False


class HelperQuickPanel(QWidget):
    """画布右下角的辅助对象快速调节面板"""

    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self._updating = False
        self.setFixedWidth(230)
        self.setStyleSheet(
            "HelperQuickPanel { background: rgba(30,30,30,225);"
            " border: 1px solid #00a0ff; border-radius: 4px; }")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(8, 6, 8, 6)
        self.lay.setSpacing(4)
        self.title = QLabel(u"")
        self.title.setStyleSheet("color:#ffffff; font-weight:bold;")
        self.lay.addWidget(self.title)
        self.rows = {}
        self.setVisible(False)
        canvas.selectionChanged.connect(self.refresh)

    def _add(self, key, label, lo, hi, val, decimals=3):
        row = _SliderRow(label, lo, hi, decimals)
        row.set_value(val)
        # ★ 滚轮步长 = 网格间距（显示单位 = snap_spacing / 10）
        row.set_wheel_step_provider(
            lambda: max(0.001, self.canvas.snap_spacing / 10.0))
        row.valueChanged.connect(lambda v, k=key: self._on_changed(k, v))
        self.lay.addWidget(row)
        self.rows[key] = row

    def _clear(self):
        # ★ 清空全部子 widget，然后重新把 title 加回布局首位
        while self.lay.count() > 0:
            item = self.lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                if w is not self.title:
                    w.deleteLater()
        self.rows.clear()
        self.lay.addWidget(self.title)  # title 永远在首位

    def update_values(self):
        """轻量刷新：只更新现有滑块/spin 的值，不重建控件。
        拖动辅助对象时每帧调用，性能友好。"""
        if not self.isVisible():
            return
        sel = self.canvas.selected_helpers
        if len(sel) != 1:
            return
        h = sel[0]
        self._updating = True
        try:
            if isinstance(h, HelperPoint):
                if 'x' in self.rows: self.rows['x'].set_value(h.dx() * 2)
                if 'y' in self.rows: self.rows['y'].set_value(h.dy() * 2)
            elif isinstance(h, HelperLine):
                if 'len' in self.rows:
                    self.rows['len'].set_value(self.canvas._line_length(h))
                if 'ang' in self.rows:
                    self.rows['ang'].set_value(self.canvas._line_angle(h))
                if 'cx' in self.rows:
                    cx = (h.dx1() + h.dx2()) / 2.0
                    self.rows['cx'].set_value(cx * 2)
                if 'cy' in self.rows:
                    cy = (h.dy1() + h.dy2()) / 2.0
                    self.rows['cy'].set_value(cy * 2)
            elif isinstance(h, HelperCircle) and h.point is not None:
                if 'x' in self.rows: self.rows['x'].set_value(h.point.dx() * 2)
                if 'y' in self.rows: self.rows['y'].set_value(h.point.dy() * 2)
                if 'r' in self.rows: self.rows['r'].set_value(h.dr() * 2)
        except Exception:
            pass
        finally:
            self._updating = False

    def refresh(self):
        sel = self.canvas.selected_helpers
        if len(sel) != 1:
            self.setVisible(False)
            return
        # ★ 先隐藏，避免切换瞬间看到旧行/新行叠加的错乱
        self.setVisible(False)
        self._updating = True
        try:
            h = sel[0]
            self._clear()
            shown = False
            if isinstance(h, HelperPoint):
                self.title.setText(
                    u"● %s" % (h.name or _L(u"点", u"Point")))
                self._add("x", u"X", -4, 4, h.dx() * 2)
                self._add("y", u"Y", -4, 4, h.dy() * 2)
                shown = True
            elif isinstance(h, HelperLine):
                self.title.setText(
                    u"／ %s" % (h.name or _L(u"线", u"Line")))
                self._add("len", _L(u"长度", u"Length"),
                          0.01, 20.0, self.canvas._line_length(h))
                self._add("ang", _L(u"角度°", u"Angle°"),
                          -180.0, 180.0,
                          self.canvas._line_angle(h), 1)
                cx = (h.dx1() + h.dx2()) / 2.0
                cy = (h.dy1() + h.dy2()) / 2.0
                self._add("cx", _L(u"中心X", u"CenterX"), -4, 4, cx * 2)
                self._add("cy", _L(u"中心Y", u"CenterY"), -4, 4, cy * 2)
                shown = True
            elif isinstance(h, HelperCircle) and h.point is not None:
                self.title.setText(
                    u"○ %s" % (h.name or _L(u"圆", u"Circle")))
                self._add("x", u"X", -4, 4, h.point.dx() * 2)
                self._add("y", u"Y", -4, 4, h.point.dy() * 2)
                self._add("r", _L(u"半径", u"Radius"),
                          0.02, 4.0, h.dr() * 2)
                shown = True
        finally:
            self._updating = False
        if not shown:
            self.setVisible(False)
            return
        self.adjustSize()
        self._reposition()
        self.setVisible(True)
        self.raise_()  # ★ 确保面板在最上层

    def _on_changed(self, key, v):
        if self._updating: return
        sel = self.canvas.selected_helpers
        if len(sel) != 1: return
        h = sel[0]
        if isinstance(h, HelperPoint):
            if key == 'x':
                h.use_expr_x = False; h.x = v / 2.0
            elif key == 'y':
                h.use_expr_y = False; h.y = v / 2.0
        elif isinstance(h, HelperLine):
            h.use_expr_x1 = h.use_expr_y1 = False
            h.use_expr_x2 = h.use_expr_y2 = False
            if key == 'len':
                self.canvas.set_line_length(h, v)
            elif key == 'ang':
                self.canvas.set_line_angle(h, v)
            elif key == 'cx':
                d = v / 2.0 - (h.dx1() + h.dx2()) / 2.0
                h.x1 += d;
                h.x2 += d
            elif key == 'cy':
                d = v / 2.0 - (h.dy1() + h.dy2()) / 2.0
                h.y1 += d;
                h.y2 += d
        elif isinstance(h, HelperCircle):
            if key == 'x' and h.point:
                h.point.use_expr_x = False;
                h.point.x = v / 2.0
            elif key == 'y' and h.point:
                h.point.use_expr_y = False;
                h.point.y = v / 2.0
            elif key == 'r':
                h.use_expr_r = False;
                h.radius = v / 2.0
        self.canvas.eval_all(0.0)
        self.canvas.update()
        self.canvas.contentChanged.emit()
        # ★ 同步其他行的显示值
        self.update_values()

    def _reposition(self):
        cw = self.canvas.width();
        ch = self.canvas.height()
        self.move(max(0, cw - self.width() - 12),
                  max(0, ch - self.height() - 12))

    def wheelEvent(self, e):
        """★ 快速面板里的滚轮事件在此消费掉，不让它冒泡到 Canvas。
        · 滑块 / 数值框上的滚轮已由 _SliderRow.eventFilter 拦截（用于调值）
        · label / 空白区的滚轮本来没用，消费掉避免触发画布缩放
        """
        e.accept()


# ==================================================================== 画布
class _FakeCenter(object):
    """拖动线中心时的"虚拟对象"包装。
    _set_display_pos 会检查这个对象的 bind_to / bind_dx 等字段，
    处理完后再调用 sync_back() 把值写回真正的 line。
    """

    def __init__(self, ln):
        self.ln = ln
        self.bind_to = getattr(ln, 'bind_to', u"")
        self.bind_dx = getattr(ln, 'bind_dx', 0.0)
        self.bind_dy = getattr(ln, 'bind_dy', 0.0)
        self.bind_dx_expr = getattr(ln, 'bind_dx_expr', u"")
        self.bind_dy_expr = getattr(ln, 'bind_dy_expr', u"")

    def sync_back(self):
        self.ln.bind_to = self.bind_to
        self.ln.bind_dx = self.bind_dx
        self.ln.bind_dy = self.bind_dy
        self.ln.bind_dx_expr = self.bind_dx_expr
        self.ln.bind_dy_expr = self.bind_dy_expr


class Canvas(QWidget):
    selectionChanged = pyqtSignal()
    geometryChanged = pyqtSignal()
    contentChanged = pyqtSignal()
    itemsChanged = pyqtSignal()
    requestEditText = pyqtSignal()
    bindPicked = pyqtSignal(object)
    requestContextMenu = pyqtSignal(object, float, float)  # globalPos, worldX, worldY
    HANDLE_TOL = 8;
    ROT_TOL = 12;
    ROT_OFFSET = 34.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setMinimumSize(300, 300)
        self.root = Node(name=u"根", folder=True)
        self.selected = []
        self.zoom = 200.0
        self.pan = QPointF(0.0, 0.0)
        self.canvas_w = 1.0;
        self.canvas_h = 1.0
        self.global_size = DEFAULT_GLOBAL_SIZE
        self.glyph_ratio = DEFAULT_GLYPH_RATIO
        self.variables = {}
        self.current_time = 0.0
        self.show_bounds = True;
        self.show_grid = True
        self.show_ruler = True
        self.snap_enabled = True;
        self.snap_spacing = 1.0
        self.mode = None;
        self.active = None
        self._drag_start_world = QPointF();
        self._drag_states = []
        self._scale_start_dist = 1.0
        self._scale_start_size = DEFAULT_GLOBAL_SIZE
        self._rot_center_screen = QPointF()
        self._rot_start_angle = 0.0;
        self._rot_start_value = 0.0
        self._pan_anchor = QPointF();
        self._fitted = False
        self._mouse_world = QPointF(0.0, 0.0)
        self.run_test_active = False
        self.helper_points = []
        self.helper_circles = []
        self.helper_lines = []
        self._helper_name_seq = {'P': 0, 'L': 0, 'C': 0}
        self.selected_helpers = []
        self.helper_tool = None
        self._helper_drag_info = None
        self._rubber_start = None
        self._rubber_end = None
        self._rubber_press_pos = None
        self.snap_helpers = True
        self.helper_locked = False
        self._group_seq = 0
        self._char_seq = 0
        self.bind_pick_mode = False
        self._quick_panel = HelperQuickPanel(self)
        self._context_hit_obj = None

    # ============ 树操作 ============
    @property
    def items(self):
        out = []

        def visit(n):
            if n.folder:
                for c in n.children: visit(c)
            elif n.item is not None:
                out.append(n.item)

        visit(self.root);
        return out

    # ============ 辅助点/圆/线 ============
    def _helper_hit_test(self, spos):
        """命中检测。返回 (kind, obj)。

        规则：
        · 圆的圆心命中 → 返回 ('circle_center', 圆)，
          而不是 ('point', 点)，这样圆环和圆心始终是同一个对象
        · 多个对象重叠时 → 优先返回「子级对象」（有 bind_to 的）
        · 同类未绑定时保持原有遍历顺序
        """
        hits = []
        # 1) 点（含圆的圆心）
        for p in self.helper_points:
            sc = self.world_to_screen(QPointF(p.dx(), p.dy()))
            if self._near(spos, sc, 10):
                owner = None
                for c in self.helper_circles:
                    if c.point is p:
                        owner = c
                        break
                if owner is not None:
                    hits.append(('circle_center', owner))
                else:
                    hits.append(('point', p))
        # 2) 圆环
        for c in self.helper_circles:
            if c.point is None:
                continue
            sc = self.world_to_screen(QPointF(c.point.dx(), c.point.dy()))
            r_px = c.dr() * self.zoom
            d = math.hypot(spos.x() - sc.x(), spos.y() - sc.y())
            if abs(d - r_px) <= 8:
                hits.append(('circle', c))
        # 3) 线
        for ln in self.helper_lines:
            s1 = self.world_to_screen(QPointF(ln.dx1(), ln.dy1()))
            s2 = self.world_to_screen(QPointF(ln.dx2(), ln.dy2()))
            sm = QPointF((s1.x() + s2.x()) / 2.0, (s1.y() + s2.y()) / 2.0)
            if self._near(spos, s1, 10):
                hits.append(('line_p1', ln))
            elif self._near(spos, s2, 10):
                hits.append(('line_p2', ln))
            elif self._near(spos, sm, 10):
                hits.append(('line_mid', ln))
            elif self._point_on_segment(spos, s1, s2, 6):
                hits.append(('line', ln))
        if not hits:
            return None
        # 去重：同一个对象只保留首个命中的 kind
        seen = set()
        unique = []
        for k, o in hits:
            if id(o) not in seen:
                seen.add(id(o))
                unique.append((k, o))

        # ★ 按"吸附链深度"排序：越深的子级越优先（支持多级嵌套）
        byname = self._all_objects_by_name()

        def _depth(o):
            d = 0
            cur = o
            visited = set()
            while True:
                tgt = getattr(cur, 'bind_to', u'') or u''
                if not tgt:
                    break
                if id(cur) in visited:
                    break
                visited.add(id(cur))
                par = byname.get(tgt)
                if par is None:
                    break
                cur = par
                d += 1
                if d > 64:
                    break
            return d

        unique.sort(key=lambda kv: -_depth(kv[1]))
        return unique[0]

    def _point_on_segment(self, p, a, b, tol):
        dx = b.x() - a.x();
        dy = b.y() - a.y()
        L2 = dx * dx + dy * dy
        if L2 < 1e-9:
            return self._near(p, a, tol)
        t = ((p.x() - a.x()) * dx + (p.y() - a.y()) * dy) / L2
        t = max(0.0, min(1.0, t))
        return (abs(p.x() - (a.x() + t * dx)) <= tol and
                abs(p.y() - (a.y() + t * dy)) <= tol)

    def _proj_to_segment(self, x, y, x1, y1, x2, y2):
        dx = x2 - x1;
        dy = y2 - y1
        L2 = dx * dx + dy * dy
        if L2 < 1e-9: return x1, y1
        t = ((x - x1) * dx + (y - y1) * dy) / L2
        t = max(0.0, min(1.0, t))
        return x1 + t * dx, y1 + t * dy

    def _find_nearby_point(self, x, y, thresh):
        best = None;
        bd = thresh
        for p in self.helper_points:
            d = math.hypot(x - p.dx(), y - p.dy())
            if d < bd: bd = d; best = p
        return best

    def _line_length(self, ln):
        return math.hypot(ln.dx2() - ln.dx1(), ln.dy2() - ln.dy1())

    def _line_angle(self, ln):
        return math.degrees(math.atan2(ln.dy2() - ln.dy1(),
                                       ln.dx2() - ln.dx1()))

    def set_line_length(self, ln, new_len):
        new_len = float(new_len)
        if new_len <= 1e-6: return
        ln.use_expr_x1 = ln.use_expr_y1 = False
        ln.use_expr_x2 = ln.use_expr_y2 = False
        L = self._line_length(ln)
        if L < 1e-9: return
        a = math.radians(self._line_angle(ln))
        cx = (ln.x1 + ln.x2) / 2.0
        cy = (ln.y1 + ln.y2) / 2.0
        hx = new_len / 2.0 * math.cos(a)
        hy = new_len / 2.0 * math.sin(a)
        ln.x1 = cx - hx;
        ln.y1 = cy - hy
        ln.x2 = cx + hx;
        ln.y2 = cy + hy

    def set_line_angle(self, ln, new_angle):
        ln.use_expr_x1 = ln.use_expr_y1 = False
        ln.use_expr_x2 = ln.use_expr_y2 = False
        a = math.radians(float(new_angle))
        L = self._line_length(ln)
        if L < 1e-9: L = 0.5
        cx = (ln.x1 + ln.x2) / 2.0
        cy = (ln.y1 + ln.y2) / 2.0
        hx = L / 2.0 * math.cos(a)
        hy = L / 2.0 * math.sin(a)
        ln.x1 = cx - hx;
        ln.y1 = cy - hy
        ln.x2 = cx + hx;
        ln.y2 = cy + hy

    def _helper_pos_snapshot(self, h):
        if isinstance(h, HelperPoint):
            return (h.dx(), h.dy())
        if isinstance(h, HelperLine):
            return ((h.dx1() + h.dx2()) / 2.0,
                    (h.dy1() + h.dy2()) / 2.0)
        if isinstance(h, HelperCircle):
            if h.point:
                return (h.point.dx(), h.point.dy())
            return (0.0, 0.0)
        return (0.0, 0.0)

    def _move_helper_group(self, primary, dx, dy):
        if dx == 0 and dy == 0: return
        if not getattr(primary, 'group_id', None): return
        gid = primary.group_id
        seen_pts = set()
        if isinstance(primary, HelperPoint):
            seen_pts.add(id(primary))
        elif isinstance(primary, HelperCircle) and primary.point:
            seen_pts.add(id(primary.point))
        for h in self.helper_points:
            if h is primary or h.group_id != gid or id(h) in seen_pts: continue
            seen_pts.add(id(h))
            h.x += dx;
            h.y += dy
        for h in self.helper_lines:
            if h is primary or h.group_id != gid: continue
            h.x1 += dx;
            h.y1 += dy;
            h.x2 += dx;
            h.y2 += dy
        for h in self.helper_circles:
            if h is primary or h.group_id != gid: continue
            if h.point and id(h.point) not in seen_pts:
                seen_pts.add(id(h.point))
                h.point.x += dx;
                h.point.y += dy

    def _apply_helper_drag(self, wpos):
        k = self._helper_drag_info
        if k is None: return
        kind, obj, extra = k
        # ★ 拖动时自动关闭该对象的表达式，转为静态坐标
        if kind == 'point' and isinstance(obj, HelperPoint):
            obj.use_expr_x = False;
            obj.use_expr_y = False
        elif isinstance(obj, HelperLine):
            obj.use_expr_x1 = False;
            obj.use_expr_y1 = False
            obj.use_expr_x2 = False;
            obj.use_expr_y2 = False

        byname = self._all_objects_by_name()

        def _bind_owner(o):
            """若 o 是某个被绑定圆的点 → 返回那个圆；否则返回 o"""
            if isinstance(o, HelperPoint):
                for c in self.helper_circles:
                    if c.point is o and getattr(c, 'bind_to', u""):
                        return c
            return o

        def _set_display_pos(o, nx, ny):
            """把新的世界位置写回对象：
            · 若对象（或它所属的圆）被绑定 → 反推并更新相对偏移
            · 否则 → 写静态 x/y
            两种情况下都同步 _disp_*，画布立即跟随
            """
            bt = _bind_owner(o)
            tgt = getattr(bt, 'bind_to', u"") or u""
            parent = byname.get(tgt) if tgt else None
            if parent is not None and parent is not bt:
                px, py = self._obj_pos(parent)
                parent_rot = self._obj_rot(parent)
                a = math.radians(-parent_rot)
                wx = nx - px
                wy = ny - py
                bt.bind_dx = wx * math.cos(a) - wy * math.sin(a)
                bt.bind_dy = wx * math.sin(a) + wy * math.cos(a)
                # 拖动 = 覆盖成静态偏移（清空动态表达式）
                bt.bind_dx_expr = u""
                bt.bind_dy_expr = u""
                # ★ 若绑定对象是圆，同步刷新它圆心的显示缓存
                #   （否则拖动圆心时，apply_bindings 会用旧缓存反推 → 瞬移）
                if isinstance(bt, HelperCircle) and bt.point is not None:
                    bt.point._disp_x = nx
                    bt.point._disp_y = ny
            else:
                # ★ 扣掉 FT 叠加偏移，让显示位置 == 鼠标拖到位置
                try:
                    dwx, dwy, _ = self._compute_extra_offset(o)
                except Exception:
                    dwx, dwy = 0.0, 0.0
                o.x = nx - dwx
                o.y = ny - dwy
            # 立即刷新显示，避免拖动一帧延迟
            try:
                if isinstance(o, HelperPoint):
                    o._disp_x = nx
                    o._disp_y = ny
            except Exception:
                pass

        old_snap = self._helper_pos_snapshot(obj)

        if kind == 'point':
            if extra is not None:
                smx, smy, sox, soy = extra
                nx = sox + (wpos.x() - smx)
                ny = soy + (wpos.y() - smy)
            else:
                nx, ny = wpos.x(), wpos.y()
            if self.snap_enabled:
                nx = self._snap_world(nx)
                ny = self._snap_world(ny)
            sx, sy = self._snap_pos_to_helpers(nx, ny, 12.0 / self.zoom)
            if (sx, sy) != (nx, ny):
                nx, ny = sx, sy
            _set_display_pos(obj, nx, ny)
        elif kind == 'circle':
            # ★ 拖动圆环 → 改半径
            cx = obj.point.dx()
            cy = obj.point.dy()
            dx = wpos.x() - cx
            dy = wpos.y() - cy
            r = math.hypot(dx, dy)
            if self.snap_enabled: r = self._snap_world(r)
            obj.radius = max(0.01, r)
            obj._disp_r = None  # 用新半径刷新显示
        elif kind == 'circle_center':
            # ★ 拖动圆心 → 移动整个圆（增量式，不瞬移）
            c = obj
            if extra is not None:
                smx, smy, sox, soy = extra
                nx = sox + (wpos.x() - smx)
                ny = soy + (wpos.y() - smy)
            else:
                nx, ny = wpos.x(), wpos.y()
            if self.snap_enabled:
                nx = self._snap_world(nx)
                ny = self._snap_world(ny)
            sx, sy = self._snap_pos_to_helpers(
                nx, ny, 12.0 / self.zoom, exclude=c.point)
            if (sx, sy) != (nx, ny):
                nx, ny = sx, sy
            if c.point is not None:
                _set_display_pos(c.point, nx, ny)
        elif kind in ('line_create', 'line_p1', 'line_p2'):
            ln = obj
            if extra is not None and kind in ('line_p1', 'line_p2'):
                smx, smy, sox, soy = extra
                nx = sox + (wpos.x() - smx)
                ny = soy + (wpos.y() - smy)
            else:
                nx, ny = wpos.x(), wpos.y()
            p = self._find_nearby_point(nx, ny, 12.0 / self.zoom)
            if p is not None:
                nx, ny = p.dx(), p.dy()
            elif self.snap_enabled:
                nx = self._snap_world(nx)
                ny = self._snap_world(ny)
                sx, sy = self._snap_pos_to_helpers(
                    nx, ny, 12.0 / self.zoom, exclude=ln)
                if (sx, sy) != (nx, ny): nx, ny = sx, sy
            if kind == 'line_create':
                ln.x2 = nx
                ln.y2 = ny
                ln._disp_x2 = nx
                ln._disp_y2 = ny
            elif kind == 'line_p1':
                ln.x1 = nx
                ln.y1 = ny
                ln._disp_x1 = nx
                ln._disp_y1 = ny
            else:
                ln.x2 = nx
                ln.y2 = ny
                ln._disp_x2 = nx
                ln._disp_y2 = ny
        elif kind == 'line_move':
            ln = obj
            dx = wpos.x() - extra[0]
            dy = wpos.y() - extra[1]
            extra[0] = wpos.x()
            extra[1] = wpos.y()
            cx = (ln.dx1() + ln.dx2()) / 2.0
            cy = (ln.dy1() + ln.dy2()) / 2.0
            fc = _FakeCenter(ln)
            _set_display_pos(fc, cx + dx, cy + dy)
            fc.sync_back()
        elif kind == 'line_mid':
            ln = obj
            if extra is not None:
                smx, smy, sox, soy = extra
                nx = sox + (wpos.x() - smx)
                ny = soy + (wpos.y() - smy)
            else:
                nx, ny = wpos.x(), wpos.y()
            if self.snap_enabled:
                nx = self._snap_world(nx)
                ny = self._snap_world(ny)
            sx, sy = self._snap_pos_to_helpers(
                nx, ny, 12.0 / self.zoom, exclude=ln)
            if (sx, sy) != (nx, ny): nx, ny = sx, sy
            fc = _FakeCenter(ln)
            _set_display_pos(fc, nx, ny)
            fc.sync_back()

        # ★ group 整体平移同步
        if kind in ('point', 'circle_center', 'line_move', 'line_mid'):
            new_snap = self._helper_pos_snapshot(obj)
            ddx = new_snap[0] - old_snap[0]
            ddy = new_snap[1] - old_snap[1]
            if ddx or ddy:
                self._move_helper_group(obj, ddx, ddy)

        # ★ 应用绑定：拖动辅助对象时子字符/子对象立即跟随
        try:
            self.apply_bindings(6)
        except Exception:
            pass
        self.update()
        # ★ 实时刷新右下角面板数值（不重建控件）
        try:
            self._quick_panel.update_values()
        except Exception:
            pass

        # ★ group 整体平移同步
        if kind in ('point', 'line_move', 'line_mid'):
            new_snap = self._helper_pos_snapshot(obj)
            ddx = new_snap[0] - old_snap[0]
            ddy = new_snap[1] - old_snap[1]
            if ddx or ddy:
                self._move_helper_group(obj, ddx, ddy)

        # ★ 应用绑定：拖动辅助对象时子字符/子对象立即跟随
        try:
            self.apply_bindings(6)
        except Exception:
            pass
        self.update()
        # ★ 实时刷新右下角面板数值（不重建控件）
        try:
            self._quick_panel.update_values()
        except Exception:
            pass

    def _snap_pos_to_helpers(self, x, y, thresh, exclude=None):
        bx, by, bd = x, y, thresh
        for p in self.helper_points:
            if p is exclude: continue
            d = math.hypot(x - p.dx(), y - p.dy())
            if d < bd: bd = d; bx, by = p.dx(), p.dy()
        for c in self.helper_circles:
            if c is exclude or c.point is None: continue
            cx, cy = c.point.dx(), c.point.dy()
            dx = x - cx;
            dy = y - cy
            r = math.hypot(dx, dy)
            if r < 1e-9: continue
            rr = c.dr()
            px = cx + rr * dx / r
            py = cy + rr * dy / r
            d = abs(r - rr)
            if d < bd: bd = d; bx, by = px, py
        for ln in self.helper_lines:
            if ln is exclude: continue
            px, py = self._proj_to_segment(x, y, ln.dx1(), ln.dy1(),
                                           ln.dx2(), ln.dy2())
            d = math.hypot(x - px, y - py)
            if d < bd: bd = d; bx, by = px, py
        return bx, by

    def _is_point_selected(self, hp):
        """点被直接选中，或它所属的圆被选中，都算选中"""
        try:
            for x in self.selected_helpers:
                if x is hp:
                    return True
                if isinstance(x, HelperCircle) and x.point is hp:
                    return True
        except Exception:
            pass
        return False

    def _draw_helpers(self, p):
        for hp in self.helper_points:
            if not getattr(hp, 'visible', True): continue
            sc = self.world_to_screen(QPointF(hp.dx(), hp.dy()))
            sel = self._is_point_selected(hp)
            col = QColor("#00cc66") if sel else QColor("#ff6600")
            p.setPen(QPen(col, 2))
            p.setBrush(QBrush(QColor(col.red(), col.green(), col.blue(), 60)))
            p.drawEllipse(sc, 6, 6)
            p.setBrush(Qt.NoBrush)
            p.drawLine(QPointF(sc.x() - 12, sc.y()), QPointF(sc.x() + 12, sc.y()))
            p.drawLine(QPointF(sc.x(), sc.y() - 12), QPointF(sc.x(), sc.y() + 12))
        for c in self.helper_circles:
            if not getattr(c, 'visible', True): continue
            if c.point is None: continue
            sc = self.world_to_screen(QPointF(c.point.dx(), c.point.dy()))
            r_px = c.dr() * self.zoom
            sel = any(c is x for x in self.selected_helpers)
            col = QColor("#00cc66") if sel else QColor("#0099ff")
            pen = QPen(col, 1);
            pen.setStyle(Qt.DashLine)
            p.setPen(pen);
            p.setBrush(Qt.NoBrush)
            if r_px > 0.5: p.drawEllipse(sc, r_px, r_px)
        for ln in self.helper_lines:
            if not getattr(ln, 'visible', True): continue
            s1 = self.world_to_screen(QPointF(ln.dx1(), ln.dy1()))
            s2 = self.world_to_screen(QPointF(ln.dx2(), ln.dy2()))
            sm = QPointF((s1.x() + s2.x()) / 2.0, (s1.y() + s2.y()) / 2.0)
            sel = any(ln is x for x in self.selected_helpers)
            col = QColor("#00cc66") if sel else QColor("#ff6600")
            p.setPen(QPen(col, 2));
            p.setBrush(Qt.NoBrush)
            p.drawLine(s1, s2)
            p.setBrush(QBrush(QColor("#ffffff")))
            for pt in (s1, s2):
                p.drawEllipse(pt, 4, 4)
            p.setBrush(QBrush(QColor("#ffee00")))
            p.drawEllipse(sm, 5, 5)

    # ============ 辅助对象树 & 名字 ============
    def _next_helper_name(self, kind):
        self._helper_name_seq[kind] = self._helper_name_seq.get(kind, 0) + 1
        prefix = {'P': u'点', 'L': u'线', 'C': u'圆'}.get(kind, kind)
        return u"%s%d" % (prefix, self._helper_name_seq[kind])

    def _next_char_name(self):
        # ★ 先从树里所有已有字符名同步序号（防止加载工程后 _char_seq 归零）
        #   再检查重名（防止 _char_seq 落后于工程内容）
        found_max = [self._char_seq]
        existing = set()

        def visit(n):
            it = getattr(n, 'item', None)
            if it is not None:
                nm = getattr(it, 'name', u"") or u""
                if nm:
                    existing.add(nm)
                    m = re.match(r'^(?:字符|Char)(\d+)$', nm)
                    if m:
                        try:
                            found_max[0] = max(found_max[0], int(m.group(1)))
                        except Exception:
                            pass
            if n.folder:
                for c in n.children:
                    visit(c)

        visit(self.root)
        self._char_seq = found_max[0]

        # ★ 继续向后找，直到中文、英文两种格式都不重名
        while True:
            self._char_seq += 1
            name_zh = u"字符%d" % self._char_seq
            name_en = u"Char%d" % self._char_seq
            if name_zh not in existing and name_en not in existing:
                return _L(name_zh, name_en)

    # ============ 绑定系统 ============
    def _all_objects_by_name(self):
        m = {}

        def visit(n):
            h = getattr(n, 'helper', None)
            if h is not None and getattr(h, 'name', u""):
                m[h.name] = h
            it = getattr(n, 'item', None)
            if it is not None and getattr(it, 'name', u""):
                m[it.name] = it
            if n.folder:
                for c in n.children: visit(c)

        visit(self.root)
        return m

    def _is_bound_to_line_or_circle(self, obj):
        """判断对象是否吸附在辅助线或辅助圆上。
        用于禁止拖动：吸附到线/圆上的元素位置由公式决定，
        手动拖动会和绑定公式冲突。
        · 字符：绑到线/圆 → 禁止拖动
        · 辅助对象：绑到线/圆 → 禁止拖动（圆心的绑定由圆负责）
        · 绑到字符上：不受影响，仍可拖动
        """
        try:
            # 圆心的绑定实际由圆负责，先找到所属的圆
            owner = obj
            if isinstance(obj, HelperPoint):
                for c in self.helper_circles:
                    if c.point is obj:
                        owner = c
                        break
            tgt = getattr(owner, 'bind_to', u'') or u''
            if not tgt:
                return False
            byname = self._all_objects_by_name()
            parent = byname.get(tgt)
            if parent is None:
                return False
            return isinstance(parent, (HelperLine, HelperCircle))
        except Exception:
            return False

    def _obj_pos(self, obj):
        if isinstance(obj, RichItem):
            return obj.disp_center()
        if isinstance(obj, HelperPoint):
            return (obj.dx(), obj.dy())
        if isinstance(obj, HelperLine):
            return ((obj.dx1() + obj.dx2()) / 2.0,
                    (obj.dy1() + obj.dy2()) / 2.0)
        if isinstance(obj, HelperCircle):
            if obj.point:
                return (obj.point.dx(), obj.point.dy())
        return (0.0, 0.0)

    def _obj_rot(self, obj):
        # 统一约定：正值 = 视觉逆时针
        if isinstance(obj, RichItem):
            return obj.disp_rotation()
        if isinstance(obj, HelperLine):
            # 屏幕 atan2 是顺时针正，取负转成视觉逆时针
            return -math.degrees(math.atan2(obj.dy2() - obj.dy1(),
                                            obj.dx2() - obj.dx1()))
        return 0.0

    def _eval_bind_field(self, obj, expr_attr, val_attr):
        s = getattr(obj, expr_attr, u"") or u""
        s = s.strip()
        if not s:
            return float(getattr(obj, val_attr, 0.0))
        try:
            byname = self.helper_by_name()
            s = self._resolve_helper_refs(s, byname)
        except Exception as ex:
            import sys
            print(u"[bind] resolve 失败: %r | expr=%r" % (ex, s), file=sys.stderr)
            return float(getattr(obj, val_attr, 0.0))
        wrapped = s if (s.startswith('{') and s.endswith('}')) else ('{' + s + '}')
        try:
            r = eval_text_stateful(wrapped, self.variables, 0.0,
                                   ExprState(), id(obj))
            return float(r)
        except Exception as ex:
            import sys
            print(u"[bind] eval 失败: %r | expr=%s"
                  % (ex, wrapped[:200]), file=sys.stderr)
            return float(getattr(obj, val_attr, 0.0))

    def debug_bind_info(self, obj):
        """诊断：打印绑定公式、解析结果、求值结果，定位滑动失效原因。"""
        lines = []
        tgt = getattr(obj, 'bind_to', u"")
        nm = getattr(obj, 'name', u"") or u"?"
        lines.append(u"对象: %s" % nm)
        if not tgt:
            lines.append(u"  → 未绑定")
            return u"\n".join(lines)
        lines.append(u"  绑定到: %s" % tgt)
        dxe = getattr(obj, 'bind_dx_expr', u"") or u""
        dye = getattr(obj, 'bind_dy_expr', u"") or u""
        ane = getattr(obj, 'bind_angle_expr', u"") or u""
        lines.append(u"  bind_dx_expr    = %r" % dxe)
        lines.append(u"  bind_dy_expr    = %r" % dye)
        lines.append(u"  bind_angle_expr = %r" % ane)
        try:
            byname = self.helper_by_name()
            lines.append(u"  可用辅助对象: %s"
                         % (u", ".join(list(byname.keys())) or u"(无)"))
        except Exception as ex:
            lines.append(u"  helper_by_name 异常: %r" % (ex,))
            return u"\n".join(lines)
        for expr_attr, val_attr, label in (
                ('bind_dx_expr', 'bind_dx', 'dx'),
                ('bind_dy_expr', 'bind_dy', 'dy'),
                ('bind_angle_expr', 'bind_angle', 'angle')):
            raw = getattr(obj, expr_attr, u"") or u""
            if not raw.strip():
                lines.append(u"  [%s] 空 → 用静态值 %s=%r"
                             % (label, val_attr, getattr(obj, val_attr, 0.0)))
                continue
            try:
                resolved = self._resolve_helper_refs(raw, byname)
            except Exception as ex:
                resolved = u"<解析异常: %r>" % (ex,)
            lines.append(u"  [%s] 解析后 = %r" % (label, resolved))
            try:
                v = self._eval_bind_field(obj, expr_attr, val_attr)
                lines.append(u"  [%s] 求值   = %r" % (label, v))
            except Exception as ex:
                lines.append(u"  [%s] 求值异常 = %r" % (label, ex))
        # 当前变量快照
        try:
            v1 = self.variables.get('Activate1', None)
            lines.append(u"  当前 Activate1 = %r" % v1)
        except Exception:
            pass
        return u"\n".join(lines)

    def _eval_bind_field_str(self, obj, expr_attr, val_attr):
        """和 _eval_bind_field 类似，但返回表达式字符串（不带外层花括号）"""
        s = getattr(obj, expr_attr, u"") or u""
        s = s.strip()
        if s:
            if s.startswith('{') and s.endswith('}'):
                return s[1:-1]
            return s
        return _fmt(getattr(obj, val_attr, 0.0))

    # ★ 通用：给 custom_pos/vo/rot 表达式求值
    def _eval_custom_expr(self, obj, expr):
        s = (expr or u'').strip()
        if not s:
            return None
        if s.startswith('{') and s.endswith('}'):
            inner = s[1:-1]
        else:
            inner = s
        # 去掉 ;fmt 后缀
        depth = 0
        in_str = False
        semi = -1
        for i, ch in enumerate(inner):
            if ch == '"':
                in_str = not in_str
            elif in_str:
                continue
            elif ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            elif ch == ';' and depth == 0:
                semi = i
                break
        if semi >= 0:
            inner = inner[:semi]
        inner = inner.strip()
        if not inner:
            return None
        try:
            if not (inner.startswith('{') and inner.endswith('}')):
                wrapped = '{' + inner + '}'
            else:
                wrapped = inner
            r = eval_text_stateful(wrapped, self.variables, 0.0,
                                   ExprState(), id(obj) + 9000)
            return float(r)
        except Exception:
            return None

    def _compute_extra_offset(self, obj):
        """返回 (dwx, dwy, drot)：叠加在世界坐标上的偏移量与旋转增量"""
        dwx = 0.0
        dwy = 0.0
        drot = 0.0
        try:
            if getattr(obj, 'custom_pos_enabled', False):
                v = self._eval_custom_expr(obj, getattr(obj, 'custom_pos_expr', u''))
                if v is not None:
                    dwx = v / POS_PER_WORLD
            if getattr(obj, 'custom_vo_enabled', False):
                v = self._eval_custom_expr(obj, getattr(obj, 'custom_vo_expr', u''))
                if v is not None:
                    dwy = -v / VO_PER_WORLD
            if getattr(obj, 'custom_rot_enabled', False):
                v = self._eval_custom_expr(obj, getattr(obj, 'custom_rot_expr', u''))
                if v is not None:
                    drot = v
        except Exception:
            pass
        return dwx, dwy, drot

    def _apply_bind_one(self, obj, byname):
        tgt = getattr(obj, 'bind_to', u"")
        if not tgt: return
        parent = byname.get(tgt)
        if parent is None or parent is obj: return
        px, py = self._obj_pos(parent)
        # 位置：用父对象世界旋转，把父本地偏移转回世界
        parent_rot = self._obj_rot(parent)
        a = math.radians(-parent_rot)
        dx = self._eval_bind_field(obj, 'bind_dx_expr', 'bind_dx')
        dy = self._eval_bind_field(obj, 'bind_dy_expr', 'bind_dy')
        rx = dx * math.cos(a) - dy * math.sin(a)
        ry = dx * math.sin(a) + dy * math.cos(a)
        nx = px + rx
        ny = py + ry
        # 子对象世界旋转 = 父世界旋转 + 相对角
        bang = self._eval_bind_field(obj, 'bind_angle_expr', 'bind_angle')
        child_rot = parent_rot + bang

        # ★ 统一叠加用户自定义 pos/vo/rot（字符 / 点 / 线 / 圆 通用）
        #   这样父对象被 FT 位移后，子孙对象会在下一轮迭代里读到新位置，
        #   实现"嵌套位移"。
        dwx, dwy, drot = self._compute_extra_offset(obj)
        nx += dwx
        ny += dwy
        child_rot += drot

        if isinstance(obj, RichItem):
            obj._disp_x = nx
            obj._disp_y = ny
            obj._disp_rot = child_rot
        elif isinstance(obj, HelperPoint):
            obj._disp_x = nx
            obj._disp_y = ny
        elif isinstance(obj, HelperLine):
            # ★ 用显示端点算长度（线端点可能由 FT / 拖动驱动，
            #   静态 x1/x2 不反映实际长度）
            L = math.hypot(obj.dx2() - obj.dx1(), obj.dy2() - obj.dy1())
            if L < 1e-9:
                L = 0.5
            fa = math.radians(-child_rot)
            hx = L / 2 * math.cos(fa)
            hy = L / 2 * math.sin(fa)
            obj._disp_x1 = nx - hx
            obj._disp_y1 = ny - hy
            obj._disp_x2 = nx + hx
            obj._disp_y2 = ny + hy
        elif isinstance(obj, HelperCircle):
            if obj.point:
                obj.point._disp_x = nx
                obj.point._disp_y = ny

    def apply_bindings(self, iterations=5):
        byname = self._all_objects_by_name()
        for _ in range(iterations):
            for it in self.items:
                self._apply_bind_one(it, byname)
            for h in self.helper_points:
                self._apply_bind_one(h, byname)
            for h in self.helper_lines:
                self._apply_bind_one(h, byname)
            for h in self.helper_circles:
                self._apply_bind_one(h, byname)

    def append_helper_node(self, helper, target=None):
        target = target or self.root
        n = Node(folder=False, helper=helper, parent=target)
        target.children.append(n)
        self._resync_helper_lists()
        return n

    def create_helper_at(self, kind, wx, wy):
        """从右键菜单直接创建辅助对象：
        · 点：立即放置
        · 线：右键位置为第一端点，等左键点击第二端点
        · 圆：右键位置为圆心，等左键点击确定半径
        """
        if self.snap_enabled:
            wx = self._snap_world(wx)
            wy = self._snap_world(wy)
        new_helper = None
        if kind == 'point':
            p = HelperPoint(wx, wy, name=self._next_helper_name('P'))
            self.append_helper_node(p)
            new_helper = p
            self.itemsChanged.emit()
            self.contentChanged.emit()
        elif kind == 'line':
            ln = HelperLine(wx, wy, wx, wy,
                            name=self._next_helper_name('L'))
            self.append_helper_node(ln)
            new_helper = ln
            self.itemsChanged.emit()
            self._helper_drag_info = ('line_create', ln, None)
            self.mode = 'helper'
        elif kind == 'circle':
            p = HelperPoint(wx, wy, name=self._next_helper_name('P'))
            self.append_helper_node(p)
            c = HelperCircle(p, 0.25, name=self._next_helper_name('C'))
            self.append_helper_node(c)
            new_helper = c
            self.itemsChanged.emit()
            self._helper_drag_info = ('circle', c, None)
            self.mode = 'helper'
        # ★ 自动选中新对象 → 触发右下角面板显示
        if new_helper is not None:
            self.selected = []
            self.selected_helpers = [new_helper]
            self.selectionChanged.emit()
        self.update()

    def find_helper_node(self, helper):
        def visit(n):
            if n.helper is helper: return n
            if n.folder:
                for c in n.children:
                    r = visit(c)
                    if r is not None: return r
            return None

        return visit(self.root)

    def _resync_helper_lists(self):
        pts, cirs, lins = [], [], []

        def visit(n):
            h = getattr(n, 'helper', None)
            if isinstance(h, HelperPoint):
                pts.append(h)
            elif isinstance(h, HelperCircle):
                cirs.append(h)
            elif isinstance(h, HelperLine):
                lins.append(h)
            if n.folder:
                for c in n.children: visit(c)

        visit(self.root)
        self.helper_points = pts
        self.helper_circles = cirs
        self.helper_lines = lins

    def helper_by_name(self):
        m = {}

        def visit(n):
            h = getattr(n, 'helper', None)
            if h is not None and getattr(h, 'name', u""):
                m[h.name] = h
            if n.folder:
                for c in n.children: visit(c)

        visit(self.root)
        return m

    def _resolve_helper_refs(self, expr, byname, depth=0, _max_len=20000,
                             _visiting=None):
        """把 {P1_X} 等辅助对象引用替换成它们的表达式或数值。
        ★ 手写字符扫描，不用正则（正则的 [^}]+? 在长串上会灾难性回溯 → 闪退）"""
        if not expr or '{' not in expr: return expr
        if depth > 6: return expr
        if len(expr) > _max_len: return expr
        if _visiting is None:
            _visiting = set()

        out = []
        last = 0
        total = 0
        i = 0
        n = len(expr)
        try:
            while i < n:
                if expr[i] != '{':
                    i += 1
                    continue
                j = expr.find('}', i + 1)
                if j < 0:
                    break
                inner = expr[i + 1:j]
                k = inner.rfind('_')
                if k <= 0:
                    i = j + 1
                    continue
                name = inner[:k]
                field = inner[k + 1:]
                if not field or not field.isalnum():
                    i = j + 1
                    continue
                # 命中 {name_field}
                out.append(expr[last:i])
                total += i - last
                last = j + 1
                h = byname.get(name)
                repl = None
                if h is not None and id(h) not in _visiting:
                    raw = self._helper_field_expr(h, field)
                    if len(raw) <= _max_len:
                        inner_res = self._resolve_helper_refs(
                            raw, byname, depth + 1, _max_len,
                                         _visiting | {id(h)})
                        if len(inner_res) <= _max_len:
                            repl = u"(" + inner_res + u")"
                if repl is None:
                    out.append(expr[i:j + 1])
                    total += j + 1 - i
                else:
                    out.append(repl)
                    total += len(repl)
                if total > _max_len:
                    return expr
                i = j + 1
            out.append(expr[last:])
            result = u"".join(out)
        except RecursionError:
            return expr
        if len(result) > _max_len:
            return expr
        return result

    @staticmethod
    def _helper_field_expr(h, field):
        f = field.upper()
        if isinstance(h, HelperPoint):
            if f == 'X':
                return h.expr_x if (h.use_expr_x and h.expr_x.strip()) else _fmt(h.x)
            if f == 'Y':
                return h.expr_y if (h.use_expr_y and h.expr_y.strip()) else _fmt(h.y)
        elif isinstance(h, HelperLine):
            for i, (ex, ey, ux, uy, sx, sy) in enumerate((
                    (h.expr_x1, h.expr_y1, h.use_expr_x1, h.use_expr_y1,
                     h.x1, h.y1),
                    (h.expr_x2, h.expr_y2, h.use_expr_x2, h.use_expr_y2,
                     h.x2, h.y2))):
                if f == 'X%d' % (i + 1):
                    return ex if (ux and ex.strip()) else _fmt(sx)
                if f == 'Y%d' % (i + 1):
                    return ey if (uy and ey.strip()) else _fmt(sy)
        elif isinstance(h, HelperCircle):
            if f == 'R':
                return h.expr_r if (h.use_expr_r and h.expr_r.strip()) else _fmt(h.radius)
            if f == 'X':
                return _fmt(h.point.x) if h.point else u"0"
            if f == 'Y':
                return _fmt(h.point.y) if h.point else u"0"
        return u"0"

    def eval_helpers(self):
        byname = self.helper_by_name()
        # ★ 预先把"属于圆的点"挑出来，避免它们的 _disp_* 被重复设置
        circle_pts = set()
        for c in self.helper_circles:
            if c.point is not None:
                circle_pts.add(id(c.point))

        for _ in range(5):
            for h in self.helper_points:
                # 由圆负责它自己的点
                if id(h) in circle_pts:
                    continue
                dwx, dwy, _ = self._compute_extra_offset(h)
                if h.use_expr_x and h.expr_x.strip():
                    v = self._eval_helper_expr(h.expr_x, byname, h)
                    h._disp_x = (v + dwx) if v is not None else None
                else:
                    h._disp_x = (h.x + dwx) if abs(dwx) > 1e-12 else None
                if h.use_expr_y and h.expr_y.strip():
                    v = self._eval_helper_expr(h.expr_y, byname, h)
                    h._disp_y = (v + dwy) if v is not None else None
                else:
                    h._disp_y = (h.y + dwy) if abs(dwy) > 1e-12 else None
            for h in self.helper_lines:
                dwx, dwy, _ = self._compute_extra_offset(h)
                # X1
                if h.use_expr_x1 and h.expr_x1.strip():
                    v = self._eval_helper_expr(h.expr_x1, byname, h)
                    h._disp_x1 = (v + dwx) if v is not None else None
                else:
                    h._disp_x1 = (h.x1 + dwx) if abs(dwx) > 1e-12 else None
                # Y1
                if h.use_expr_y1 and h.expr_y1.strip():
                    v = self._eval_helper_expr(h.expr_y1, byname, h)
                    h._disp_y1 = (v + dwy) if v is not None else None
                else:
                    h._disp_y1 = (h.y1 + dwy) if abs(dwy) > 1e-12 else None
                # X2
                if h.use_expr_x2 and h.expr_x2.strip():
                    v = self._eval_helper_expr(h.expr_x2, byname, h)
                    h._disp_x2 = (v + dwx) if v is not None else None
                else:
                    h._disp_x2 = (h.x2 + dwx) if abs(dwx) > 1e-12 else None
                # Y2
                if h.use_expr_y2 and h.expr_y2.strip():
                    v = self._eval_helper_expr(h.expr_y2, byname, h)
                    h._disp_y2 = (v + dwy) if v is not None else None
                else:
                    h._disp_y2 = (h.y2 + dwy) if abs(dwy) > 1e-12 else None
            for h in self.helper_circles:
                dwx, dwy, _ = self._compute_extra_offset(h)
                if h.point is not None:
                    pt = h.point
                    if pt.use_expr_x and pt.expr_x.strip():
                        v = self._eval_helper_expr(pt.expr_x, byname, pt)
                        pt._disp_x = (v + dwx) if v is not None else None
                    else:
                        pt._disp_x = (pt.x + dwx) if abs(dwx) > 1e-12 else None
                    if pt.use_expr_y and pt.expr_y.strip():
                        v = self._eval_helper_expr(pt.expr_y, byname, pt)
                        pt._disp_y = (v + dwy) if v is not None else None
                    else:
                        pt._disp_y = (pt.y + dwy) if abs(dwy) > 1e-12 else None
                if h.use_expr_r and h.expr_r.strip():
                    v = self._eval_helper_expr(h.expr_r, byname, h)
                    h._disp_r = v
                else:
                    h._disp_r = None

    def _eval_helper_expr(self, expr, byname, self_obj):
        s = expr.strip()
        if not s: return None
        s = self._resolve_helper_refs(s, byname)
        if not (s.startswith('{') and s.endswith('}')):
            s = '{' + s + '}'
        try:
            r = eval_text_stateful(s, self.variables, 0.0, ExprState(), id(self_obj))
            return float(r)
        except Exception:
            return None

    def append_item(self, item, target=None):
        target = target or self.root
        n = Node(folder=False, item=item, parent=target)
        target.children.append(n);
        return n

    def find_node(self, item):
        def visit(n):
            if not n.folder and n.item is item: return n
            if n.folder:
                for c in n.children:
                    r = visit(c)
                    if r is not None: return r
            return None

        return visit(self.root)

    def remove_item(self, item):
        n = self.find_node(item)
        if n is not None and n.parent is not None: n.parent.children.remove(n)

    def set_items_list(self, items):
        self.root.children = []
        for it in items: self.append_item(it)

    def eval_all(self, dt=0.0):
        self.eval_helpers()
        byname = self.helper_by_name()
        for it in self.items:
            saved = (it.custom_pos_expr, it.custom_vo_expr,
                     it.custom_size_expr, it.custom_rot_expr)
            try:
                it.custom_pos_expr = self._resolve_helper_refs(saved[0], byname)
                it.custom_vo_expr = self._resolve_helper_refs(saved[1], byname)
                it.custom_size_expr = self._resolve_helper_refs(saved[2], byname)
                it.custom_rot_expr = self._resolve_helper_refs(saved[3], byname)
                it.eval_display(self.variables, dt, use_expr=True)
            finally:
                (it.custom_pos_expr, it.custom_vo_expr,
                 it.custom_size_expr, it.custom_rot_expr) = saved
        # ★ 应用绑定
        self.apply_bindings()

    # ============ 标尺偏移 ============
    def _ruler_off_x(self):
        return RULER_SIZE if self.show_ruler else 0

    def _ruler_off_y(self):
        return RULER_SIZE if self.show_ruler else 0

    def world_to_screen(self, p):
        return QPointF(self.pan.x() + p.x() * self.zoom + self._ruler_off_x(),
                       self.pan.y() + p.y() * self.zoom + self._ruler_off_y())

    def screen_to_world(self, p):
        return QPointF((p.x() - self.pan.x() - self._ruler_off_x()) / self.zoom,
                       (p.y() - self.pan.y() - self._ruler_off_y()) / self.zoom)

    # ============ 世界 ↔ 显示值（画布边缘 = ±1） ============
    def _world_to_disp_x(self, wx):
        return wx * 2.0 / max(1e-9, self.canvas_w)

    def _world_to_disp_y(self, wy):
        return wy * 2.0 / max(1e-9, self.canvas_h)

    def _disp_to_world_x(self, dv):
        return dv * self.canvas_w / 2.0

    def _disp_to_world_y(self, dv):
        return dv * self.canvas_h / 2.0

    def _px_per_disp_x(self):
        return self.zoom * self.canvas_w / 2.0

    def _px_per_disp_y(self):
        return self.zoom * self.canvas_h / 2.0

    def x_half(self):
        return self.canvas_w / 2.0

    def y_half(self):
        return self.canvas_h / 2.0

    def pos_half(self):
        return POS_HALF_PER_CANVAS * self.canvas_w

    def vo_half(self):
        return VO_HALF_PER_CANVAS * self.canvas_h

    def world_step(self):
        return self.snap_spacing * self.canvas_w / 20.0

    def _snap_world(self, v):
        if not self.snap_enabled: return v
        st = self.world_step()
        if st <= 1e-9: return v
        return round(v / st) * st

    def _clamp(self, x, y):
        # 允许放到画布外（世界坐标 ±1000 上限，防止极端值）
        LIM = 1000.0
        return (max(-LIM, min(LIM, x)), max(-LIM, min(LIM, y)))

    # ============ 尺寸/度量 ============
    def font_px(self, it):
        return it.disp_size() * FONT_SIZE_UNIT * self.zoom

    def _layout_display(self, it):
        disp = it.display_text()
        base_px = max(1.0, self.font_px(it))
        base_font = it.make_font(base_px)
        base_fm = QFontMetricsF(base_font)
        if not disp:
            return [], 1.0, 1.0, base_fm, base_font
        if '<' not in disp:
            fm = QFontMetricsF(it.make_font(base_px))
            w = max(1.0, fm.horizontalAdvance(disp))
            h = max(1.0, fm.height())
            f = it.make_font(base_px)
            default_st = {
                'size': 1.0, 'color': None, 'rotate': 0.0, 'alpha': 1.0,
                'pos': 0.0, 'voffset': 0.0, 'bold': False, 'italic': False,
                'scale': 1.0, 'cspace': 0.0, 'mspace': 0.0, 'mark': None,
                'underline': False, 'strike': False,
            }
            char_list = [(c, default_st, f, fm, fm.horizontalAdvance(c))
                         for c in disp]
            return char_list, w, h, base_fm, base_font
        segments = parse_rich_tags(disp, self.variables)
        char_list = []
        total_w = 0.0;
        cur_line_w = 0.0
        max_h = 0.0;
        cur_line_h = 0.0
        for ch, st in segments:
            if ch == '\n':
                if cur_line_w > total_w: total_w = cur_line_w
                cur_line_w = 0.0
                max_h += cur_line_h if cur_line_h > 0 else base_px
                cur_line_h = 0.0
                continue
            px = max(1.0, base_px * st['size'])
            f = it.make_font(px, st['bold'], st['italic'])
            fm_c = QFontMetricsF(f)
            if 'space_width_em' in st:
                cw = st['space_width_em'] * px
            else:
                cw = fm_c.horizontalAdvance(ch) * st.get('scale', 1.0)
                cw += st.get('cspace', 0.0) + st.get('mspace', 0.0)
            char_list.append((ch, st, f, fm_c, cw))
            cur_line_w += cw
            if fm_c.height() > cur_line_h: cur_line_h = fm_c.height()
        if cur_line_w > total_w: total_w = cur_line_w
        max_h += cur_line_h if cur_line_h > 0 else base_px
        return char_list, max(1.0, total_w), max(1.0, max_h), base_fm, base_font

    def item_metrics(self, it):
        char_list, w, h, base_fm, base_font = self._layout_display(it)
        return base_font, base_fm, w, h, it.display_text()

    # ============ 命中/手柄 ============
    def hit_test(self, spos):
        for it in reversed(self.items):
            if it.hidden: continue
            dc_x, dc_y = it.disp_center()
            sc = self.world_to_screen(QPointF(dc_x, dc_y))
            dx = spos.x() - sc.x();
            dy = spos.y() - sc.y()
            a = math.radians(it.disp_rotation())
            lx = dx * math.cos(a) + dy * math.sin(a)
            ly = -dx * math.sin(a) + dy * math.cos(a)
            _, _, w, h, _ = self.item_metrics(it)
            if abs(lx) <= w / 2.0 + 4 and abs(ly) <= h / 2.0 + 4:
                return it
        return None

    # ★ 蓝框纵向半高（标尺单位，画布边缘 = ±1）
    HANDLE_HALF_VO = 0.07

    def handle_positions(self, it):
        _, _, w, h_orig, _ = self.item_metrics(it)
        size_uses_expr = bool(it.custom_size_enabled
                              and it.custom_size_expr.strip())
        special = size_uses_expr and not it.compensate_offset

        # ★ 用表达式求值后的实际位置
        dc_x, dc_y = it.disp_center()
        sc = self.world_to_screen(QPointF(dc_x, dc_y))

        if special:
            G = self.global_size
            # ★ 用函数求值后的实际 size，失败才回落到数值框
            C = it._disp_size if it._disp_size is not None else it.size
            if C <= 1e-9: C = 1.0
            # 蓝框高度与字形联动（与默认模式同一比例）
            box_h = h_orig * (0.07 / 0.12)
            # ★ 底边固定在 世界 y = item.y + 0.07·G·(canvas_h/2)
            #   换算到屏幕：bottom_offset = 0.07·G·(canvas_h/2)·zoom
            #   屏幕 y 向下为正 → 底边在 sc 下方
            y_half = self.canvas_h / 2.0
            bottom_offset = 0.07 * G * y_half * self.zoom
            #   中心 = 底边上方 box_h/2
            center = QPointF(sc.x(), sc.y() + bottom_offset - box_h / 2.0)
            box_w = w
        else:
            box_h = h_orig * (0.07 / 0.12)
            center = sc
            box_w = w

        # ★ 用表达式求值后的实际旋转（绑定对象由父对象决定）
        a = math.radians(-it.disp_rotation())
        ca, sa = math.cos(a), math.sin(a)

        def local(lx, ly):
            return QPointF(center.x() + lx * ca - ly * sa,
                           center.y() + lx * sa + ly * ca)

        hw, hh = box_w / 2.0, box_h / 2.0
        corners = [local(-hw, -hh), local(hw, -hh), local(hw, hh), local(-hw, hh)]
        mids = [local(0, -hh), local(hw, 0), local(0, hh), local(-hw, 0)]
        up = mids[0]
        d = QPointF(up.x() - center.x(), up.y() - center.y())
        n = math.hypot(d.x(), d.y())
        if n > 1e-6:
            d = QPointF(d.x() / n * self.ROT_OFFSET, d.y() / n * self.ROT_OFFSET)
        else:
            d = QPointF(0, -self.ROT_OFFSET)
        return up + d, corners, mids

    @staticmethod
    def _near(p, q, tol):
        return abs(p.x() - q.x()) <= tol and abs(p.y() - q.y()) <= tol

    # ============ 标尺绘制 ============
    def _pick_ruler_steps(self):
        px_per_disp = self._px_per_disp_x()
        candidates = [
            (0.001, 0.0005, 0.0001, 4),
            (0.005, 0.001, 0.0005, 3),
            (0.01, 0.005, 0.001, 3),
            (0.02, 0.01, 0.005, 2),
            (0.05, 0.01, 0.005, 2),
            (0.1, 0.05, 0.01, 2),
            (0.2, 0.1, 0.02, 1),
            (0.5, 0.1, 0.05, 1),
            (1.0, 0.5, 0.1, 0),
            (2.0, 1.0, 0.5, 0),
            (5.0, 1.0, 0.5, 0),
            (10.0, 5.0, 1.0, 0),
        ]
        for major, mid, minor, dec in candidates:
            if major * px_per_disp >= 40:
                return major, mid, minor, dec
        return 10.0, 5.0, 1.0, 0

    @staticmethod
    def _fmt_ruler(v, decimals):
        if abs(v) < 1e-12: return u"0"
        s = (u"%.*f" % (decimals, v)).rstrip(u"0").rstrip(u".")
        if s in (u"-0", u""): s = u"0"
        return s

    def _draw_h_ruler(self, p):
        w = self.width()
        # 背景
        p.fillRect(QRectF(0, 0, w, RULER_SIZE), QColor("#2a2a2a"))
        p.fillRect(QRectF(0, 0, RULER_SIZE, RULER_SIZE), QColor("#333333"))
        p.setPen(QPen(QColor("#555"), 1))
        p.drawLine(QPointF(0, RULER_SIZE - 0.5),
                   QPointF(w, RULER_SIZE - 0.5))
        p.drawLine(QPointF(RULER_SIZE - 0.5, 0),
                   QPointF(RULER_SIZE - 0.5, RULER_SIZE))

        px_per_disp = self._px_per_disp_x()
        if px_per_disp <= 0: return
        major, mid, minor, dec = self._pick_ruler_steps()
        if minor <= 0: return

        # 用屏幕中心反推可见显示值范围
        c_disp = self._world_to_disp_x(
            self.screen_to_world(QPointF(w / 2.0, 0)).x())
        half_disp = (w / 2.0) / px_per_disp
        dv0 = c_disp - half_disp
        dv1 = c_disp + half_disp

        start_i = int(math.floor(dv0 / minor)) - 1
        end_i = int(math.ceil(dv1 / minor)) + 1
        if end_i - start_i > 1000: return

        fm = QFontMetricsF(p.font())
        major_px = major * px_per_disp
        num_alpha = 1.0 if major_px >= 40 else max(0.0, (major_px - 22.0) / 18.0)

        for i in range(start_i, end_i + 1):
            dv = i * minor
            wx = self._disp_to_world_x(dv)
            sx = self.world_to_screen(QPointF(wx, 0)).x()
            if sx < RULER_SIZE - 0.5 or sx > w + 0.5: continue
            is_major = abs((dv / major) - round(dv / major)) < 1e-6
            is_mid = abs((dv / mid) - round(dv / mid)) < 1e-6
            if is_major:
                p.setPen(QPen(QColor("#dddddd"), 1))
                p.drawLine(QPointF(sx, RULER_SIZE - 10),
                           QPointF(sx, RULER_SIZE - 1))
                if num_alpha > 0.05:
                    txt = u"0" if abs(dv) < 1e-9 else self._fmt_ruler(dv, dec)
                    tw = fm.horizontalAdvance(txt)
                    col = QColor("#dddddd");
                    col.setAlphaF(num_alpha)
                    p.setPen(QPen(col, 1))
                    p.drawText(QPointF(sx - tw / 2.0, RULER_SIZE - 12), txt)
            elif is_mid:
                p.setPen(QPen(QColor("#999999"), 1))
                p.drawLine(QPointF(sx, RULER_SIZE - 6),
                           QPointF(sx, RULER_SIZE - 1))
            else:
                p.setPen(QPen(QColor("#666666"), 1))
                p.drawLine(QPointF(sx, RULER_SIZE - 3),
                           QPointF(sx, RULER_SIZE - 1))

    def _draw_v_ruler(self, p):
        h = self.height()
        p.fillRect(QRectF(0, RULER_SIZE, RULER_SIZE, h - RULER_SIZE),
                   QColor("#2a2a2a"))
        p.setPen(QPen(QColor("#555"), 1))
        p.drawLine(QPointF(RULER_SIZE - 0.5, RULER_SIZE),
                   QPointF(RULER_SIZE - 0.5, h))

        px_per_disp = self._px_per_disp_y()
        if px_per_disp <= 0: return
        major, mid, minor, dec = self._pick_ruler_steps()
        if minor <= 0: return

        c_disp = self._world_to_disp_y(
            self.screen_to_world(QPointF(0, h / 2.0)).y())
        half_disp = (h / 2.0) / px_per_disp
        dv0 = c_disp - half_disp
        dv1 = c_disp + half_disp

        start_i = int(math.floor(dv0 / minor)) - 1
        end_i = int(math.ceil(dv1 / minor)) + 1
        if end_i - start_i > 1000: return

        fm = QFontMetricsF(p.font())
        major_px = major * px_per_disp
        num_alpha = 1.0 if major_px >= 40 else max(0.0, (major_px - 22.0) / 18.0)

        for i in range(start_i, end_i + 1):
            dv = i * minor
            wy = self._disp_to_world_y(dv)
            sy = self.world_to_screen(QPointF(0, wy)).y()
            if sy < RULER_SIZE - 0.5 or sy > h + 0.5: continue
            is_major = abs((dv / major) - round(dv / major)) < 1e-6
            is_mid = abs((dv / mid) - round(dv / mid)) < 1e-6
            if is_major:
                p.setPen(QPen(QColor("#dddddd"), 1))
                p.drawLine(QPointF(RULER_SIZE - 10, sy),
                           QPointF(RULER_SIZE - 1, sy))
                if num_alpha > 0.05:
                    txt = u"0" if abs(dv) < 1e-9 else self._fmt_ruler(dv, dec)
                    p.save()
                    p.translate(RULER_SIZE - 12, sy)
                    p.rotate(-90)
                    tw = fm.horizontalAdvance(txt)
                    col = QColor("#dddddd");
                    col.setAlphaF(num_alpha)
                    p.setPen(QPen(col, 1))
                    p.drawText(QPointF(-tw / 2.0, 0), txt)
                    p.restore()
            elif is_mid:
                p.setPen(QPen(QColor("#999999"), 1))
                p.drawLine(QPointF(RULER_SIZE - 6, sy),
                           QPointF(RULER_SIZE - 1, sy))
            else:
                p.setPen(QPen(QColor("#666666"), 1))
                p.drawLine(QPointF(RULER_SIZE - 3, sy),
                           QPointF(RULER_SIZE - 1, sy))

    # ============ 绘制主流程 ============
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.fillRect(self.rect(), QColor("#242424"))

        tl = self.world_to_screen(QPointF(-self.x_half(), -self.y_half()))
        br = self.world_to_screen(QPointF(self.x_half(), self.y_half()))
        canvas_rect = QRectF(tl, br)
        p.fillRect(canvas_rect, QColor("#ffffff"))

        if self.show_grid:
            step = self.world_step()
            if step > 1e-6 and step * self.zoom >= 4:
                # 画布内：深色网格
                pen = QPen(QColor(0, 0, 0, 26));
                pen.setCosmetic(True)
                p.setPen(pen)
                nx = int(round(self.x_half() / step))
                for i in range(-nx, nx + 1):
                    xw = i * step
                    p.drawLine(self.world_to_screen(QPointF(xw, -self.y_half())),
                               self.world_to_screen(QPointF(xw, self.y_half())))
                ny = int(round(self.y_half() / step))
                for i in range(-ny, ny + 1):
                    yw = i * step
                    p.drawLine(self.world_to_screen(QPointF(-self.x_half(), yw)),
                               self.world_to_screen(QPointF(self.x_half(), yw)))

                # 画布外：浅色虚线网格（虚空网格）
                pen2 = QPen(QColor(255, 255, 255, 22))
                pen2.setCosmetic(True)
                pen2.setStyle(Qt.DotLine)
                p.setPen(pen2)
                # 可见世界范围（含画布外）
                w0 = self.screen_to_world(QPointF(0, 0))
                w1 = self.screen_to_world(QPointF(self.width(), self.height()))
                # 遍历整个可见区域的网格线
                x_min = math.floor(w0.x() / step) * step
                x_max = math.ceil(w1.x() / step) * step
                y_min = math.floor(w0.y() / step) * step
                y_max = math.ceil(w1.y() / step) * step

                xs = x_min
                cnt = 0
                while xs <= x_max and cnt < 3000:
                    if abs(xs) > self.x_half() + 1e-9:
                        s_top = self.world_to_screen(QPointF(xs, w0.y()))
                        s_bot = self.world_to_screen(QPointF(xs, w1.y()))
                        p.drawLine(s_top, s_bot)
                    xs += step
                    cnt += 1
                ys = y_min
                cnt = 0
                while ys <= y_max and cnt < 3000:
                    if abs(ys) > self.y_half() + 1e-9:
                        s_l = self.world_to_screen(QPointF(w0.x(), ys))
                        s_r = self.world_to_screen(QPointF(w1.x(), ys))
                        p.drawLine(s_l, s_r)
                    ys += step
                    cnt += 1

        pen = QPen(QColor(0, 0, 0, 70));
        pen.setCosmetic(True);
        p.setPen(pen)
        c = self.world_to_screen(QPointF(0, 0))
        p.drawLine(QPointF(c.x() - 9, c.y()), QPointF(c.x() + 9, c.y()))
        p.drawLine(QPointF(c.x(), c.y() - 9), QPointF(c.x(), c.y() + 9))

        for it in self.items:
            self._draw_item(p, it)

        pen = QPen(QColor(0, 0, 0, 110));
        pen.setCosmetic(True)
        p.setPen(pen);
        p.setBrush(Qt.NoBrush);
        p.drawRect(canvas_rect)

        if self.show_bounds:
            for it in self.selected:
                if not it.hidden:
                    self._draw_handles(p, it)

        # ★ 父对象紫色高亮（纯视觉提示，不产生任何联动）
        try:
            self._draw_parent_highlights(p)
        except Exception:
            pass

        self._draw_helpers(p)
        if self._rubber_start is not None and self._rubber_end is not None:
            r = QRectF(self._rubber_start, self._rubber_end).normalized()
            p.setPen(QPen(QColor("#00a0ff"), 1, Qt.DashLine))
            p.setBrush(QBrush(QColor(0, 160, 255, 40)))
            p.drawRect(r)
        # 标尺最后画
        if self.show_ruler:
            try:
                self._draw_h_ruler(p)
                self._draw_v_ruler(p)
            except Exception:
                pass

    def _draw_item(self, p, it):
        if it.hidden: return
        char_list, total_w, total_h, base_fm, base_font = self._layout_display(it)
        if not char_list: return
        base_px = self.font_px(it)
        if base_px < 1: return
        dc_x, dc_y = it.disp_center()
        sc = self.world_to_screen(QPointF(dc_x, dc_y))
        pos_off_px = it.disp_pos_world(self.canvas_w) * self.zoom
        size_uses_expr = bool(it.custom_size_enabled
                              and it.custom_size_expr.strip())
        special = size_uses_expr and not it.compensate_offset
        if special:
            # ★ 字形视觉中心 = 蓝框中心（与 handle_positions 保持一致）
            G = self.global_size
            box_h = base_fm.height() * (0.07 / 0.12)  # 与蓝框同高
            y_half = self.canvas_h / 2.0
            bottom_offset = 0.07 * G * y_half * self.zoom
            # 蓝框中心相对 sc 的屏幕偏移
            box_center_offset = bottom_offset - box_h / 2.0
            # 让字形视觉中心 = 蓝框中心
            baseline_y = box_center_offset + (base_fm.ascent() - base_fm.descent()) / 2.0
        else:
            baseline_y = -base_fm.height() / 2.0 + base_fm.ascent()
            baseline_y -= it.disp_up_world(self.canvas_h) * self.zoom

        p.save()
        p.translate(sc.x() + pos_off_px, sc.y())
        p.rotate(-it.disp_rotation())

        cursor_x = -total_w / 2.0
        line_off_y = 0.0
        line_max_h = 0.0
        for ch, st, f, fm_c, cw in char_list:
            if fm_c.height() > line_max_h: line_max_h = fm_c.height()
            draw_ch = ch
            try:
                if st.get('uppercase'):
                    draw_ch = ch.upper()
                elif st.get('lowercase'):
                    draw_ch = ch.lower()
            except Exception:
                pass
            draw_x = cursor_x + st['pos']
            draw_y = baseline_y - st['voffset'] - line_off_y
            p.save()
            if abs(st['rotate']) > 0.01:
                cx = draw_x + cw / 2.0
                cy = draw_y - base_fm.ascent() / 2.0
                p.translate(cx, cy);
                p.rotate(-st['rotate']);
                p.translate(-cx, -cy)
            if st.get('mark') is not None:
                mk = QColor(st['mark'])
                ma = st.get('mark_alpha', 1.0)
                if ma < 1.0:
                    a = mk.alphaF() * ma
                    mk.setAlphaF(max(0.0, min(1.0, a)))
                p.save();
                p.setPen(Qt.NoPen);
                p.setBrush(QBrush(mk))
                p.drawRect(QRectF(draw_x, draw_y - fm_c.ascent(),
                                  cw, fm_c.height()))
                p.restore()
            p.setFont(f)
            col = QColor(st['color']) if st['color'] is not None else QColor(it.color)
            if st['alpha'] < 1.0:
                a = col.alphaF() * st['alpha']
                col.setAlphaF(max(0.0, min(1.0, a)))
            p.setPen(col)
            p.drawText(QPointF(draw_x, draw_y), draw_ch)
            if st.get('underline') or it.underline:
                p.save();
                p.setPen(col)
                y = draw_y + fm_c.descent() * 0.3
                p.drawLine(QPointF(draw_x, y), QPointF(draw_x + cw, y))
                p.restore()
            if st.get('strike') or it.strike:
                p.save();
                p.setPen(col)
                y = draw_y - fm_c.ascent() * 0.35
                p.drawLine(QPointF(draw_x, y), QPointF(draw_x + cw, y))
                p.restore()
            p.restore()
            cursor_x += cw
        p.restore()

    def _draw_handles(self, p, it):
        rot_pt, corners, mids = self.handle_positions(it)
        p.setPen(QPen(QColor("#00a0ff"), 1));
        p.setBrush(Qt.NoBrush)
        p.drawPolygon(QPolygonF(corners));
        p.drawLine(mids[0], rot_pt)
        p.setBrush(QBrush(QColor("#00a0ff")));
        p.drawEllipse(rot_pt, 6, 6)
        p.setBrush(QBrush(QColor("#ffffff")))
        p.setPen(QPen(QColor("#00a0ff"), 1))
        for pt in corners + mids:
            p.drawRect(QRectF(pt.x() - 4, pt.y() - 4, 8, 8))

    def _draw_parent_highlights(self, p):
        """为选中对象的父级画紫色虚线框（纯视觉，不产生联动修改）"""
        # 快速退出：没有任何选中项带绑定
        has_bind = False
        for obj in list(self.selected) + list(self.selected_helpers):
            if getattr(obj, 'bind_to', u""):
                has_bind = True
                break
        if not has_bind:
            return

        all_objs = self._all_objects_by_name()
        seen = set()
        parents = []
        for obj in list(self.selected) + list(self.selected_helpers):
            tgt = getattr(obj, 'bind_to', u"")
            if not tgt:
                continue
            par = all_objs.get(tgt)
            if par is None or par is obj:
                continue
            if id(par) in seen:
                continue
            seen.add(id(par))
            parents.append(par)
        if not parents:
            return

        pen = QPen(QColor("#a020f0"), 2)
        pen.setStyle(Qt.DashLine)
        pen.setCosmetic(True)
        for par in parents:
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            if isinstance(par, RichItem):
                if par.hidden:
                    continue
                _, _, w, h_orig, _ = self.item_metrics(par)
                dc_x, dc_y = par.disp_center()
                sc = self.world_to_screen(QPointF(dc_x, dc_y))
                box_h = h_orig * (0.07 / 0.12)
                a = math.radians(-par.disp_rotation())
                ca, sa = math.cos(a), math.sin(a)
                hw, hh = w / 2.0, box_h / 2.0
                corners = [
                    QPointF(sc.x() + (-hw) * ca - (-hh) * sa,
                            sc.y() + (-hw) * sa + (-hh) * ca),
                    QPointF(sc.x() + (hw) * ca - (-hh) * sa,
                            sc.y() + (hw) * sa + (-hh) * ca),
                    QPointF(sc.x() + (hw) * ca - (hh) * sa,
                            sc.y() + (hw) * sa + (hh) * ca),
                    QPointF(sc.x() + (-hw) * ca - (hh) * sa,
                            sc.y() + (-hw) * sa + (hh) * ca),
                ]
                p.drawPolygon(QPolygonF(corners))
            elif isinstance(par, HelperPoint):
                sc = self.world_to_screen(QPointF(par.dx(), par.dy()))
                p.drawEllipse(sc, 10, 10)
            elif isinstance(par, HelperLine):
                s1 = self.world_to_screen(QPointF(par.dx1(), par.dy1()))
                s2 = self.world_to_screen(QPointF(par.dx2(), par.dy2()))
                p.drawLine(s1, s2)
                p.drawEllipse(s1, 5, 5)
                p.drawEllipse(s2, 5, 5)
            elif isinstance(par, HelperCircle) and par.point is not None:
                sc = self.world_to_screen(QPointF(par.point.dx(),
                                                  par.point.dy()))
                r_px = par.dr() * self.zoom
                if r_px > 0.5:
                    p.drawEllipse(sc, r_px, r_px)
                else:
                    p.drawEllipse(sc, 10, 10)

    # ============ 鼠标 ============
    def mousePressEvent(self, e):
        spos = QPointF(e.pos());
        wpos = self.screen_to_world(spos)
        # 标尺区域不响应
        if self.show_ruler:
            if spos.x() < RULER_SIZE or spos.y() < RULER_SIZE:
                return
        if e.button() == Qt.MiddleButton or (
                e.button() == Qt.LeftButton and (e.modifiers() & Qt.AltModifier)):
            self.mode = 'pan';
            self._pan_anchor = spos - self.pan
            self.setCursor(Qt.ClosedHandCursor);
            return

        # ★ 吸附拾取模式：左键点击对象 → 发出 bindPicked 信号
        if self.bind_pick_mode and e.button() == Qt.LeftButton:
            try:
                hit_obj = None
                it = self.hit_test(spos)
                if it is not None:
                    hit_obj = it
                else:
                    h = self._helper_hit_test(spos)
                    if h is not None:
                        hit_obj = h[1]
                if hit_obj is not None:
                    if isinstance(hit_obj, RichItem):
                        self.selected = [hit_obj]
                        self.selected_helpers = []
                    else:
                        self.selected = []
                        self.selected_helpers = [hit_obj]
                    self.selectionChanged.emit()
                    self.update()
                    self.bindPicked.emit(hit_obj)
                else:
                    self.selected = []
                    self.selected_helpers = []
                    self.selectionChanged.emit()
                    self.update()
            except RecursionError:
                pass
            except Exception:
                import traceback
                traceback.print_exc()
            return

        # 右键：按下时先进入 rubber 模式，释放时再区分「单击弹菜单 / 拖动框选」
        if e.button() == Qt.RightButton:
            self.mode = 'rubber'
            self._rubber_start = spos
            self._rubber_end = spos
            self._rubber_press_pos = spos
            return
        if e.button() != Qt.LeftButton: return

        # ★ 正在创建中的辅助对象（右键菜单放置的线/圆），左键点击完成
        if self.mode == 'helper' and self._helper_drag_info is not None:
            self._apply_helper_drag(wpos)
            self._helper_drag_info = None
            self.mode = None
            self.contentChanged.emit()
            # ★ 完成后再次 emit → 右下角面板刷新到最终尺寸/位置
            self.selectionChanged.emit()
            self.update()
            return

        if self.helper_tool == 'point':
            p = HelperPoint(wpos.x(), wpos.y(), name=self._next_helper_name('P'))
            if self.snap_enabled:
                p.x = self._snap_world(p.x);
                p.y = self._snap_world(p.y)
            self.append_helper_node(p)
            self.itemsChanged.emit()
            self.contentChanged.emit()
            self.update();
            return
        if self.helper_tool == 'circle':
            p = self._find_nearby_point(wpos.x(), wpos.y(), 15.0 / self.zoom)
            if p is None: return
            c = HelperCircle(p, 0.01, name=self._next_helper_name('C'))
            self.append_helper_node(c)
            self.itemsChanged.emit()
            self._helper_drag_info = ('circle', c, None)
            self.mode = 'helper';
            return
        if self.helper_tool == 'line':
            nx, ny = wpos.x(), wpos.y()
            p = self._find_nearby_point(nx, ny, 12.0 / self.zoom)
            if p is not None:
                nx, ny = p.x, p.y
            elif self.snap_enabled:
                nx = self._snap_world(nx);
                ny = self._snap_world(ny)
            ln = HelperLine(nx, ny, nx, ny, name=self._next_helper_name('L'))
            self.append_helper_node(ln)
            self.itemsChanged.emit()
            self._helper_drag_info = ('line_create', ln, None)
            self.mode = 'helper';
            return

        if self.helper_tool is None:
            hit = self._helper_hit_test(spos)
            char_hit = self.hit_test(spos)
            # ★ 深度比较：同时命中辅助对象和字符时，
            #   取吸附链更深的那个
            #   例：大圆 → 小圆 → 字符1
            #      点数字1 的位置，应优先选数字1（深度2），
            #      而不是小圆（深度1）
            if hit is not None and char_hit is not None:
                try:
                    byname = self._all_objects_by_name()

                    def _chain_depth(o):
                        d = 0
                        cur = o
                        seen = set()
                        while cur is not None:
                            tgt = getattr(cur, 'bind_to', u'') or u''
                            if not tgt:
                                break
                            if id(cur) in seen:
                                break
                            seen.add(id(cur))
                            par = byname.get(tgt)
                            if par is None:
                                break
                            cur = par
                            d += 1
                            if d > 64:
                                break
                        return d

                    if _chain_depth(char_hit) >= _chain_depth(hit[1]):
                        hit = None
                except Exception:
                    pass
            if hit is not None:
                kind, obj = hit
                # ★ 选中辅助对象 → 清空字符选中
                if self.selected:
                    self.selected = []
                    self.selectionChanged.emit()
                was_selected = any(obj is x for x in self.selected_helpers)
                if e.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier):
                    if not was_selected:
                        self.selected_helpers.append(obj)
                    self.selectionChanged.emit()
                    self.update();
                    return
                if not was_selected:
                    # ★ 首次点击只做选中，不进入拖动
                    self.selected_helpers = [obj]
                    self.selectionChanged.emit()
                    self.update();
                    return
                # 已选中：可以拖动（除非被锁定）
                if self.helper_locked:
                    return
                # ★ 吸附到线/圆上的辅助对象不允许拖动（可选中，但不能拖）
                if self._is_bound_to_line_or_circle(obj):
                    return
                if kind == 'point':
                    self._helper_drag_info = ('point', obj,
                        (wpos.x(), wpos.y(), obj.dx(), obj.dy()))
                elif kind == 'circle_center':
                    # ★ 拖动圆心 → 移动整个圆（不是改半径）
                    c = obj
                    if c.point is not None:
                        self._helper_drag_info = ('circle_center', c,
                            (wpos.x(), wpos.y(),
                             c.point.dx(), c.point.dy()))
                elif kind == 'circle':
                    self._helper_drag_info = ('circle', obj, None)
                elif kind == 'line_p1':
                    self._helper_drag_info = ('line_p1', obj,
                        (wpos.x(), wpos.y(), obj.dx1(), obj.dy1()))
                elif kind == 'line_p2':
                    self._helper_drag_info = ('line_p2', obj,
                        (wpos.x(), wpos.y(), obj.dx2(), obj.dy2()))
                elif kind == 'line_mid':
                    cx0 = (obj.dx1() + obj.dx2()) / 2.0
                    cy0 = (obj.dy1() + obj.dy2()) / 2.0
                    self._helper_drag_info = ('line_mid', obj,
                        (wpos.x(), wpos.y(), cx0, cy0))
                elif kind == 'line':
                    self._helper_drag_info = ('line_move', obj, [wpos.x(), wpos.y()])
                self.mode = 'helper';
                return
        if len(self.selected) == 1 and self.show_bounds:
            it = self.selected[0]
            if not it.hidden:
                rot_pt, corners, mids = self.handle_positions(it)
                if self._near(spos, rot_pt, self.ROT_TOL):
                    self.mode = 'rotate';
                    self.active = it
                    dc_x, dc_y = it.disp_center()
                    self._rot_center_screen = self.world_to_screen(
                        QPointF(dc_x, dc_y))
                    self._rot_start_angle = math.atan2(
                        spos.y() - self._rot_center_screen.y(),
                        spos.x() - self._rot_center_screen.x())
                    self._rot_start_value = it.rotation;
                    return
                for pt in corners + mids:
                    if self._near(spos, pt, self.HANDLE_TOL):
                        self.mode = 'scale';
                        self.active = it
                        dc_x, dc_y = it.disp_center()
                        c_s = self.world_to_screen(QPointF(dc_x, dc_y))
                        self._scale_start_dist = max(4.0, math.hypot(
                            spos.x() - c_s.x(), spos.y() - c_s.y()))
                        self._scale_start_size = it.size;
                        return
        it = self.hit_test(spos)
        if it is not None:
            # ★ 选中字符 → 清空辅助对象选中
            if self.selected_helpers:
                self.selected_helpers = []
            if e.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier):
                if it not in self.selected: self.selected.append(it)
            else:
                if it not in self.selected: self.selected = [it]
            self.selectionChanged.emit()
            # ★ 吸附到线/圆上的字符不允许拖动（可选中，但不能拖）
            if self._is_bound_to_line_or_circle(it):
                self.mode = None
                self.update()
                return
            self.mode = 'move';
            self._drag_start_world = wpos
            # ★ 用显示位置作为拖动起点（绑定对象的静态位置不是它显示的位置）
            self._drag_states = []
            for x in self.selected:
                try:
                    dx0, dy0 = x.disp_center()
                except Exception:
                    dx0, dy0 = x.x, x.y
                self._drag_states.append((x, dx0, dy0))
            self.update();
            return
        if not (e.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier)):
            self.selected = []
            self.selected_helpers = []
            self.selectionChanged.emit()
        self.mode = None;
        self.update()

    def mouseMoveEvent(self, e):
        spos = QPointF(e.pos());
        wpos = self.screen_to_world(spos)
        self._mouse_world = wpos
        if self.show_ruler:
            # 只在顶部标尺区域刷新，减少重绘
            self.update(0, 0, self.width(), RULER_SIZE)
        if self.mode == 'pan':
            self.pan = spos - self._pan_anchor - QPointF(self._ruler_off_x(),
                                                         self._ruler_off_y())
            self.update();
            return
        if self.mode == 'move':
            d = wpos - self._drag_start_world
            shift = bool(e.modifiers() & Qt.ShiftModifier)
            byname = self._all_objects_by_name()
            for it, x0, y0 in self._drag_states:
                nx = x0 + d.x();
                ny = y0 + d.y()
                if not shift:
                    nx = self._snap_world(nx);
                    ny = self._snap_world(ny)
                    if self.snap_helpers:
                        sx, sy = self._snap_pos_to_helpers(nx, ny, 12.0 / self.zoom)
                        nx, ny = sx, sy
                nx, ny = self._clamp(nx, ny)
                # ★ 绑定对象：新世界位置 → 相对父对象的新偏移
                tgt = getattr(it, 'bind_to', u"") or u""
                parent = byname.get(tgt) if tgt else None
                if parent is not None and parent is not it:
                    px, py = self._obj_pos(parent)
                    parent_rot = self._obj_rot(parent)
                    a = math.radians(-parent_rot)
                    wx = nx - px
                    wy = ny - py
                    bdx = wx * math.cos(a) - wy * math.sin(a)
                    bdy = wx * math.sin(a) + wy * math.cos(a)
                    it.bind_dx = bdx
                    it.bind_dy = bdy
                    # 拖动 = 覆盖成静态偏移（清空动态表达式）
                    it.bind_dx_expr = u""
                    it.bind_dy_expr = u""
                else:
                    it.x, it.y = nx, ny
            # ★ 重新应用所有绑定，让子对象立即跟随（父对象拖动时子对象也动）
            try:
                self.apply_bindings(2)
            except Exception:
                pass
            self.update();
            self.geometryChanged.emit();
            return
        if self.mode == 'scale':
            it = self.active
            dc_x, dc_y = it.disp_center()
            c_s = self.world_to_screen(QPointF(dc_x, dc_y))
            d = math.hypot(spos.x() - c_s.x(), spos.y() - c_s.y())
            ratio = d / self._scale_start_dist
            it.size = max(0.05, min(100.0, self._scale_start_size * ratio))
            it.size_is_custom = True
            self.update();
            self.geometryChanged.emit();
            return
        if self.mode == 'rotate':
            it = self.active
            c = self._rot_center_screen
            a_now = math.atan2(spos.y() - c.y(), spos.x() - c.x())
            delta_deg = math.degrees(a_now - self._rot_start_angle)
            val = self._rot_start_value - delta_deg
            if e.modifiers() & Qt.ShiftModifier: val = round(val / 15.0) * 15.0
            it.rotation = ((val + 180.0) % 360.0) - 180.0
            self.update();
            self.geometryChanged.emit();
            return
        if self.mode == 'rubber':
            self._rubber_end = spos
            self.update()
            return
        if self.mode == 'helper':
            self._apply_helper_drag(wpos)
            return
        if self.mode is None:
            if self.bind_pick_mode:
                self.setCursor(Qt.CrossCursor)
                return
            if self.helper_tool is not None:
                self.setCursor(Qt.CrossCursor)
                return
            hit = self._helper_hit_test(spos)
            if hit is not None:
                kind, obj = hit
                # ★ 只有已选中的辅助对象才显示拖动光标
                #   未选中时保持箭头（需要先点击选中，再悬停才能拖）
                if any(obj is x for x in self.selected_helpers):
                    self.setCursor(Qt.SizeAllCursor)
                    return
            if len(self.selected) == 1 and self.show_bounds:
                it = self.selected[0]
                if not it.hidden:
                    rot_pt, corners, mids = self.handle_positions(it)
                    if self._near(spos, rot_pt, self.ROT_TOL):
                        self.setCursor(Qt.CrossCursor);
                        return
                    for pt in corners + mids:
                        if self._near(spos, pt, self.HANDLE_TOL):
                            self.setCursor(Qt.SizeFDiagCursor);
                            return
            # ★ 都不命中 → 无条件回到箭头
            self.setCursor(Qt.ArrowCursor)

    def _do_rubber_select(self):
        if self._rubber_start is None or self._rubber_end is None: return
        r = QRectF(self._rubber_start, self._rubber_end).normalized()
        sel_items = []
        for it in self.items:
            if it.hidden: continue
            dc_x, dc_y = it.disp_center()
            sc = self.world_to_screen(QPointF(dc_x, dc_y))
            if r.contains(sc): sel_items.append(it)
        self.selected = sel_items
        sel_h = []
        for p in self.helper_points:
            if r.contains(self.world_to_screen(QPointF(p.dx(), p.dy()))):
                sel_h.append(p)
        for c in self.helper_circles:
            if c.point is None:
                continue
            if r.contains(self.world_to_screen(
                    QPointF(c.point.dx(), c.point.dy()))):
                sel_h.append(c)
        for ln in self.helper_lines:
            s1 = self.world_to_screen(QPointF(ln.dx1(), ln.dy1()))
            s2 = self.world_to_screen(QPointF(ln.dx2(), ln.dy2()))
            if r.contains(s1) and r.contains(s2): sel_h.append(ln)
        self.selected_helpers = sel_h
        self.selectionChanged.emit()
        self.update()

    def mouseReleaseEvent(self, e):
        if self.mode == 'pan': self.setCursor(Qt.ArrowCursor)
        if self.mode in ('move', 'scale', 'rotate'): self.contentChanged.emit()
        if self.mode == 'helper':
            # ★ 真拖动过才触发撤销
            if self._helper_drag_info is not None:
                self.contentChanged.emit()
            self._helper_drag_info = None
        if self.mode == 'rubber':
            moved = 0
            if self._rubber_press_pos is not None and self._rubber_end is not None:
                moved = (self._rubber_end - self._rubber_press_pos).manhattanLength()
            if moved < 5:
                # ★ 单击 → 弹右键菜单
                self._rubber_start = None
                self._rubber_end = None
                self._rubber_press_pos = None
                self.update()
                try:
                    spos = QPointF(e.pos())
                    wpos = self.screen_to_world(spos)
                    # ★ 检测是否命中对象（供菜单决定显示什么）
                    hit_obj = None
                    it = self.hit_test(spos)
                    if it is not None:
                        hit_obj = it
                    else:
                        h = self._helper_hit_test(spos)
                        if h is not None:
                            hit_obj = h[1]
                    self._context_hit_obj = hit_obj
                    self.requestContextMenu.emit(e.globalPos(),
                                                 wpos.x(), wpos.y())
                except Exception:
                    pass
            else:
                # ★ 拖动 → 框选
                self._do_rubber_select()
                self._rubber_start = None
                self._rubber_end = None
                self._rubber_press_pos = None
        self.mode = None
        self.active = None
        if self.helper_tool is not None:
            self.setCursor(Qt.CrossCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        self.update()

    def mouseDoubleClickEvent(self, e):
        it = self.hit_test(QPointF(e.pos()))
        if it is not None:
            self.selected = [it];
            self.selectionChanged.emit()
            self.update();
            self.requestEditText.emit()

    def wheelEvent(self, e):
        delta = e.angleDelta().y()
        if delta == 0: return
        factor = 1.1 if delta > 0 else 1.0 / 1.1
        new_zoom = max(5.0, min(20000.0, self.zoom * factor))
        spos = QPointF(e.pos());
        w = self.screen_to_world(spos)
        self.zoom = new_zoom
        new_pan_x = spos.x() - w.x() * new_zoom - self._ruler_off_x()
        new_pan_y = spos.y() - w.y() * new_zoom - self._ruler_off_y()
        self.pan = QPointF(new_pan_x, new_pan_y)
        self.update()

    def keyPressEvent(self, e):
        k = e.key();
        mods = e.modifiers()
        if k in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_selected()
        elif k == Qt.Key_Escape:
            self.selected = []
            self.selected_helpers = []
            self.selectionChanged.emit();
            self.update()
        elif k == Qt.Key_D and (mods & Qt.ControlModifier):
            self.duplicate_selected()
        elif k == Qt.Key_A and (mods & Qt.ControlModifier):
            self.selected = list(self.items);
            self.selectionChanged.emit();
            self.update()
        elif k == Qt.Key_B:
            self.show_bounds = not self.show_bounds;
            self.update()
        elif k in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            step = 0.1 if (mods & Qt.ShiftModifier) else 0.05
            dx = dy = 0.0
            if k == Qt.Key_Left:
                dx = -step
            elif k == Qt.Key_Right:
                dx = step
            elif k == Qt.Key_Up:
                dy = -step
            else:
                dy = step
            for it in self.selected:
                it.x, it.y = self._clamp(it.x + dx, it.y + dy)
            self.update();
            self.geometryChanged.emit();
            self.contentChanged.emit()
        elif k in (Qt.Key_Equal, Qt.Key_Plus) and (mods & Qt.ControlModifier):
            for it in self.selected:
                it.size = min(100.0, it.size * 1.1);
                it.size_is_custom = True
            self.update();
            self.geometryChanged.emit();
            self.contentChanged.emit()
        elif k == Qt.Key_Minus and (mods & Qt.ControlModifier):
            for it in self.selected:
                it.size = max(0.05, it.size / 1.1);
                it.size_is_custom = True
            self.update();
            self.geometryChanged.emit();
            self.contentChanged.emit()
        elif k == Qt.Key_Q:
            for it in self.selected:
                it.rotation = ((it.rotation + 5 + 180) % 360) - 180
            self.update();
            self.geometryChanged.emit();
            self.contentChanged.emit()
        elif k == Qt.Key_E:
            for it in self.selected:
                it.rotation = ((it.rotation - 5 + 180) % 360) - 180
            self.update();
            self.geometryChanged.emit();
            self.contentChanged.emit()
        else:
            super().keyPressEvent(e)

    def delete_selected(self):
        if not self.selected and not self.selected_helpers: return
        for it in list(self.selected): self.remove_item(it)
        for obj in list(self.selected_helpers):
            # 从树里移除
            n = self.find_helper_node(obj)
            if n is not None and n.parent is not None:
                n.parent.children.remove(n)
            # 点被删时，圆也一起删
            if isinstance(obj, HelperPoint):
                for c in list(self.helper_circles):
                    if c.point is obj:
                        cn = self.find_helper_node(c)
                        if cn is not None and cn.parent is not None:
                            cn.parent.children.remove(cn)
        self._resync_helper_lists()
        self.selected = []
        self.selected_helpers = []
        self.selectionChanged.emit()
        self.itemsChanged.emit()
        self.update()
        self.contentChanged.emit()

    def duplicate_selected(self):
        if not self.selected: return
        news = []
        for it in self.selected:
            nx, ny = self._clamp(it.x + 0.1, it.y + 0.1)
            n = RichItem(it.text, nx, ny)
            n.size = it.size;
            n.size_is_custom = it.size_is_custom
            n.rotation = it.rotation;
            n.color = QColor(it.color)
            n.bold = it.bold;
            n.italic = it.italic
            n.underline = it.underline;
            n.strike = it.strike
            n.hidden = it.hidden
            n.custom_pos_expr = it.custom_pos_expr
            n.custom_pos_enabled = it.custom_pos_enabled
            n.custom_vo_expr = it.custom_vo_expr
            n.custom_vo_enabled = it.custom_vo_enabled
            n.custom_size_expr = it.custom_size_expr
            n.custom_size_enabled = it.custom_size_enabled
            n.custom_rot_expr = it.custom_rot_expr
            n.custom_rot_enabled = it.custom_rot_enabled
            self.append_item(n);
            news.append(n)
        self.selected = news
        self.selectionChanged.emit();
        self.itemsChanged.emit()
        self.update();
        self.contentChanged.emit()

    def fit_view(self):
        if self.width() < 60 or self.height() < 60: return
        m = 60.0
        w = self.width() - m - self._ruler_off_x()
        h = self.height() - m - self._ruler_off_y()
        z = max(5.0, min(w / self.canvas_w, h / self.canvas_h))
        self.zoom = z
        self.pan = QPointF(self.width() / 2.0 - self._ruler_off_x(),
                           self.height() / 2.0 - self._ruler_off_y())
        self.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if not self._fitted and self.width() > 100:
            self._fitted = True;
            self.fit_view()
        try:
            self._quick_panel._reposition()
        except Exception:
            pass


# ============================================================== 属性面板
class HelperEditor(QGroupBox):
    """选中辅助对象时显示的表达式编辑区"""

    def __init__(self, canvas, parent=None):
        super().__init__(u"辅助对象表达式", parent)
        self.canvas = canvas
        self._updating = False
        self.form = QFormLayout(self)
        self.rows = {}
        SPEC = [('x', u'X'), ('y', u'Y'),
                ('x1', u'X1'), ('y1', u'Y1'),
                ('x2', u'X2'), ('y2', u'Y2'),
                ('r', u'半径'),
                ('len', u'长度'), ('ang', u'角度°'),
                # ★ 叠加 FT 栏：在吸附结果上再做偏移
                ('pos', u'pos 偏移'), ('vo', u'voffset 偏移'),
                ('rot', u'旋转偏移')]
        for key, label in SPEC:
            w = QWidget();
            hl = QHBoxLayout(w)
            hl.setContentsMargins(0, 0, 0, 0);
            hl.setSpacing(2)
            chk = QCheckBox(u"fx");
            chk.setFixedWidth(34)
            edit = FnLineEdit(u"引用: {C1_X} {L1_X1} {P2_Y}")
            hl.addWidget(chk);
            hl.addWidget(edit, 1)
            self.form.addRow(label, w)
            self.rows[key] = (edit, chk, w)
            chk.toggled.connect(lambda v, k=key: self._apply(k))
            edit.textChanged.connect(lambda k=key: self._apply(k))
        canvas.selectionChanged.connect(self.refresh)
        self.setVisible(False)

    def _targets(self):
        return list(self.canvas.selected_helpers)

    def _get(self, h, k):
        if k == 'x' and isinstance(h, HelperPoint): return h.expr_x, h.use_expr_x
        if k == 'y' and isinstance(h, HelperPoint): return h.expr_y, h.use_expr_y
        if k == 'x' and isinstance(h, HelperCircle):
            if h.point: return h.point.expr_x, h.point.use_expr_x
            return u"", False
        if k == 'y' and isinstance(h, HelperCircle):
            if h.point: return h.point.expr_y, h.point.use_expr_y
            return u"", False
        if k == 'x1' and isinstance(h, HelperLine): return h.expr_x1, h.use_expr_x1
        if k == 'y1' and isinstance(h, HelperLine): return h.expr_y1, h.use_expr_y1
        if k == 'x2' and isinstance(h, HelperLine): return h.expr_x2, h.use_expr_x2
        if k == 'y2' and isinstance(h, HelperLine): return h.expr_y2, h.use_expr_y2
        if k == 'r' and isinstance(h, HelperCircle): return h.expr_r, h.use_expr_r
        if k == 'len' and isinstance(h, HelperLine):
            return _fmt(self.canvas._line_length(h)), False
        if k == 'ang' and isinstance(h, HelperLine):
            return _fmt(self.canvas._line_angle(h)), False
        # ★ 叠加 FT 栏：字符 / 点 / 线 / 圆 通用（使用 getattr 兜底）
        if k == 'pos':
            return (getattr(h, 'custom_pos_expr', u""),
                    getattr(h, 'custom_pos_enabled', False))
        if k == 'vo':
            return (getattr(h, 'custom_vo_expr', u""),
                    getattr(h, 'custom_vo_enabled', False))
        if k == 'rot':
            return (getattr(h, 'custom_rot_expr', u""),
                    getattr(h, 'custom_rot_enabled', False))
        return u"", False

    def _set(self, h, k, expr, use):
        if k == 'x' and isinstance(h, HelperPoint):
            h.expr_x = expr;
            h.use_expr_x = use
        elif k == 'y' and isinstance(h, HelperPoint):
            h.expr_y = expr;
            h.use_expr_y = use
        elif k == 'x' and isinstance(h, HelperCircle):
            if h.point:
                h.point.expr_x = expr
                h.point.use_expr_x = use
        elif k == 'y' and isinstance(h, HelperCircle):
            if h.point:
                h.point.expr_y = expr
                h.point.use_expr_y = use
        elif k == 'x1' and isinstance(h, HelperLine):
            h.expr_x1 = expr;
            h.use_expr_x1 = use
        elif k == 'y1' and isinstance(h, HelperLine):
            h.expr_y1 = expr;
            h.use_expr_y1 = use
        elif k == 'x2' and isinstance(h, HelperLine):
            h.expr_x2 = expr;
            h.use_expr_x2 = use
        elif k == 'y2' and isinstance(h, HelperLine):
            h.expr_y2 = expr;
            h.use_expr_y2 = use
        elif k == 'r' and isinstance(h, HelperCircle):
            h.expr_r = expr;
            h.use_expr_r = use
        elif k == 'len' and isinstance(h, HelperLine):
            try:
                self.canvas.set_line_length(h, float(expr))
            except Exception:
                pass
        elif k == 'ang' and isinstance(h, HelperLine):
            try:
                self.canvas.set_line_angle(h, float(expr))
            except Exception:
                pass
        elif k == 'pos':
            try:
                h.custom_pos_expr = expr
                h.custom_pos_enabled = use
            except Exception:
                pass
        elif k == 'vo':
            try:
                h.custom_vo_expr = expr
                h.custom_vo_enabled = use
            except Exception:
                pass
        elif k == 'rot':
            try:
                h.custom_rot_expr = expr
                h.custom_rot_enabled = use
            except Exception:
                pass

    def refresh(self):
        self._updating = True
        tgts = self._targets()
        used = set()
        for h in tgts:
            if isinstance(h, HelperPoint):
                used |= {'x', 'y', 'pos', 'vo', 'rot'}
            elif isinstance(h, HelperLine):
                used |= {'x1', 'y1', 'x2', 'y2',
                         'len', 'ang', 'pos', 'vo', 'rot'}
            elif isinstance(h, HelperCircle):
                used |= {'x', 'y', 'r', 'pos', 'vo', 'rot'}
        for k, (edit, chk, w) in self.rows.items():
            en = (k in used)
            w.setVisible(en)
            if not en: continue
            h = tgts[0]
            expr, use = self._get(h, k)
            chk.setVisible(k not in ('len', 'ang'))
            edit.blockSignals(True);
            chk.blockSignals(True)
            edit.setPlainText(expr);
            chk.setChecked(use)
            edit.blockSignals(False);
            chk.blockSignals(False)
        self.setVisible(bool(tgts))
        self._updating = False

    def _apply(self, key):
        if self._updating: return
        edit, chk, _ = self.rows[key]
        expr = edit.toPlainText()
        use = chk.isChecked()
        for h in self._targets():
            self._set(h, key, expr, use)
        self.canvas.eval_all(0.0)
        self.canvas.update()
        self.canvas.contentChanged.emit()


class BindControlDialog(QDialog):
    """吸附控制方式配置对话框"""

    def __init__(self, child, parent_obj, canvas, parent_widget=None):
        super().__init__(parent_widget)
        self.setWindowTitle(_T('bind_ctl_title'))
        self.resize(580, 440)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.child = child
        self.parent_obj = parent_obj
        self.canvas = canvas
        self._mode = 'static'  # static / slide / orbit / custom
        self._updating_expr = False  # 防止程序改表达式时触发"手改→custom"
        self._in_regen = False  # ★ 防止 _regen_expr 重入

        v = QVBoxLayout(self)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(8)

        # ---- 关系信息 ----
        cn = (getattr(child, 'name', u'')
              or _L(u'(未命名)', u'(unnamed)'))
        pn = (getattr(parent_obj, 'name', u'')
              or _L(u'(未命名)', u'(unnamed)'))
        ptype = type(parent_obj).__name__
        info = QLabel(
            _L(u"吸附关系：<b>[%s]</b>  ←  <b>[%s]</b>  (%s)",
               u"Binding: <b>[%s]</b>  ←  <b>[%s]</b>  (%s)")
            % (cn, pn, ptype))
        info.setStyleSheet(
            "color:#0066cc; padding:6px; background:#eef5ff;"
            " border:1px solid #cce0ff; border-radius:3px;")
        v.addWidget(info)

        # ---- 快捷预设 ----
        preset_gb = QGroupBox(_L(u"控制方式", u"Control Mode"))
        pg = QHBoxLayout(preset_gb)
        self.btn_preset_static = QPushButton(_L(u"静态吸附", u"Static"))
        self.btn_preset_slide = QPushButton(
            _L(u"沿辅助线滑动", u"Slide on Line"))
        self.btn_preset_orbit = QPushButton(
            _L(u"沿辅助圆旋转", u"Orbit on Circle"))
        self.btn_preset_static.setToolTip(
            _L(u"保持相对位置和角度不变",
               u"Keep relative position and angle"))
        self.btn_preset_slide.setToolTip(
            _L(u"用控制变量在父辅助线上滑动\n需要父对象是辅助线",
               u"Slide on parent helper line by control variable\n"
               u"Parent must be a helper line"))
        self.btn_preset_orbit.setToolTip(
            _L(u"沿父辅助圆圆周运动\n需要父对象是辅助圆",
               u"Orbit around parent helper circle\n"
               u"Parent must be a helper circle"))
        for b in (self.btn_preset_static, self.btn_preset_slide, self.btn_preset_orbit):
            b.setFixedHeight(26)
            pg.addWidget(b)
        pg.addStretch(1)
        v.addWidget(preset_gb)

        # ---- 参数 ----
        form = QFormLayout()
        form.setSpacing(6)

        self.edit_ctrl = QLineEdit(u"Activate1")
        self.edit_ctrl.setPlaceholderText(
            _L(u"如 Activate1 / Trim / Time / PitchAngle",
               u"e.g. Activate1 / Trim / Time / PitchAngle"))
        # ★ 给控制变量输入框挂上 Tab 自动补全
        self._ctrl_completer = _AutoCompleter(self.edit_ctrl, _all_words)
        form.addRow(_L(u"控制变量：", u"Control Var:"), self.edit_ctrl)

        self.spin_t0 = QDoubleSpinBox()
        self.spin_t0.setRange(-1000, 1000);
        self.spin_t0.setDecimals(4)
        self.spin_t0.setValue(0.0);
        self.spin_t0.setFixedWidth(90)
        self.spin_t1 = QDoubleSpinBox()
        self.spin_t1.setRange(-1000, 1000);
        self.spin_t1.setDecimals(4)
        self.spin_t1.setValue(1.0);
        self.spin_t1.setFixedWidth(90)
        t_row = QWidget()
        tr = QHBoxLayout(t_row);
        tr.setContentsMargins(0, 0, 0, 0);
        tr.setSpacing(4)
        tr.addWidget(QLabel(_L(u"起点", u"Start")))
        tr.addWidget(self.spin_t0)
        tr.addSpacing(8)
        tr.addWidget(QLabel(_L(u"终点", u"End")))
        tr.addWidget(self.spin_t1)
        tr.addStretch(1)
        form.addRow(_L(u"变量范围：", u"Range:"), t_row)

        # ★ 圆模式专用：切线 / 起始角 / 物体偏移
        self.chk_tangent = QCheckBox(
            _L(u"沿切线方向旋转", u"Rotate along tangent"))
        self.chk_tangent.setChecked(False)
        self.chk_tangent.setToolTip(
            _L(u"勾选后：物体始终朝向圆周运动的切线方向\n"
               u"不勾选：物体朝向固定，由「字符角度」决定",
               u"Checked: object always faces the tangent direction\n"
               u"Unchecked: orientation fixed, "
               u"determined by 'Char angle'"))
        self.chk_reverse = QCheckBox(_L(u"反转", u"Reverse"))
        self.chk_reverse.setChecked(False)
        self.chk_reverse.setToolTip(
            _L(u"给切线旋转值加负号（仅当勾选「沿切线方向旋转」时有效）",
               u"Negates the tangent rotation value "
               u"(only effective when 'Rotate along tangent' is on)"))
        tan_row = QWidget()
        tan_lay = QHBoxLayout(tan_row)
        tan_lay.setContentsMargins(0, 0, 0, 0)
        tan_lay.setSpacing(10)
        tan_lay.addWidget(self.chk_tangent)
        tan_lay.addWidget(self.chk_reverse)
        tan_lay.addStretch(1)
        form.addRow(_L(u"切线旋转：", u"Tangent rotation:"), tan_row)

        self.spin_start_angle = QDoubleSpinBox()
        self.spin_start_angle.setRange(-360.0, 360.0)
        self.spin_start_angle.setDecimals(2)
        self.spin_start_angle.setSingleStep(15.0)
        self.spin_start_angle.setValue(0.0)
        self.spin_start_angle.setFixedWidth(90)
        self.spin_start_angle.setSuffix(u" °")
        # ★ 快捷角度按钮（顶部=0°，顺时针为正）
        sa_row = QWidget()
        sar = QHBoxLayout(sa_row)
        sar.setContentsMargins(0, 0, 0, 0);
        sar.setSpacing(2)
        sar.addWidget(self.spin_start_angle)
        # ★ 逆时针：0°=顶、90°=左、180°=底、270°=右
        self._sa_btns = []
        for label, val in ((_L(u"↑顶", u"↑Top"), 0.0),
                           (_L(u"↓底", u"↓Bot"), 180.0),
                           (_L(u"←左", u"←L"), 90.0),
                           (_L(u"→右", u"→R"), 270.0)):
            b = QPushButton(label)
            b.setFixedHeight(22)
            b.setFixedWidth(44)
            b.clicked.connect(
                lambda c=False, v=val: self.spin_start_angle.setValue(v))
            sar.addWidget(b)
            self._sa_btns.append(b)
        sar.addStretch(1)
        form.addRow(_L(u"起始方位角：", u"Start azimuth:"), sa_row)

        self.spin_obj_offset = QDoubleSpinBox()
        self.spin_obj_offset.setRange(-360.0, 360.0)
        self.spin_obj_offset.setDecimals(2)
        self.spin_obj_offset.setSingleStep(15.0)
        self.spin_obj_offset.setValue(0.0)
        self.spin_obj_offset.setFixedWidth(100)
        self.spin_obj_offset.setSuffix(u" °")
        self.spin_obj_offset.setToolTip(
            _L(u"物体本身朝向相对切线的额外偏移\n"
               u"0° = 完全对齐切线；正值 = 视觉逆时针额外旋转",
               u"Extra orientation offset relative to tangent\n"
               u"0° = aligned with tangent; "
               u"positive = visual CCW rotation"))
        form.addRow(_L(u"字符角度：", u"Char angle:"),
                    self.spin_obj_offset)

        v.addLayout(form)

        tip = QLabel(
            _L(u"※ 起始方位角 = 「变量范围」为「起点」值时的位置\n"
               u"    注意与「起点/终点」区分\n"
               u"    圆模式：0°=顶，逆时针为正（90°=左，180°=底，270°=右）",
               u"* Start azimuth = position when the Control Var equals "
               u"the 'Start' value\n"
               u"    Do not confuse with the Start/End range\n"
               u"    Circle mode: 0°=top, CCW positive "
               u"(90°=left, 180°=bottom, 270°=right)"))
        tip.setWordWrap(True)
        tip.setStyleSheet(
            "color:#d0a020; font-size:13px; font-weight:bold;"
            "background:#2a2418; border:1px solid #806020;"
            "border-radius:4px; padding:8px;")
        v.addWidget(tip)

        v.addStretch(1)

        # ---- 按钮 ----
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton(_L(u"确定", u"OK"))
        cancel = QPushButton(_L(u"取消", u"Cancel"))
        ok.setFixedHeight(26)
        cancel.setFixedHeight(26)
        ok.setDefault(True)
        row.addWidget(ok);
        row.addWidget(cancel)
        v.addLayout(row)

        # ---- 信号 ----
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        self.btn_preset_static.clicked.connect(lambda: self._set_mode('static'))
        self.btn_preset_slide.clicked.connect(lambda: self._set_mode('slide'))
        self.btn_preset_orbit.clicked.connect(lambda: self._set_mode('orbit'))
        # 控制变量 / 起终点 / 切线 / 起始角 / 物体偏移 改变 → 重新生成公式
        self.edit_ctrl.textChanged.connect(self._on_param_changed)
        self.spin_t0.valueChanged.connect(self._on_param_changed)
        self.spin_t1.valueChanged.connect(self._on_param_changed)
        self.chk_tangent.toggled.connect(self._on_param_changed)
        self.chk_reverse.toggled.connect(self._on_param_changed)
        self.spin_start_angle.valueChanged.connect(self._on_param_changed)
        self.spin_obj_offset.valueChanged.connect(self._on_param_changed)
        self._load_current()

    # ---------------- 工具 ----------------
    def _safe_set_plain(self, edit, text):
        """只在内容变化时才 setPlainText，并屏蔽信号，避免信号风暴/重入"""
        try:
            if edit.toPlainText() == text:
                return
        except Exception:
            pass
        try:
            edit.blockSignals(True)
            edit.setPlainText(text)
        finally:
            try:
                edit.blockSignals(False)
            except Exception:
                pass

    # ---------------- 模式管理 ----------------
    def _set_mode(self, mode):
        # ★ 控制方式由父对象类型自动决定，按钮只做指示，不能点击切换
        return

    def _update_ui_state(self):
        en_slide = self._mode in ('slide', 'orbit')
        self.edit_ctrl.setEnabled(en_slide)
        self.spin_t0.setEnabled(en_slide)
        self.spin_t1.setEnabled(en_slide)
        # ★ 切线相关只在圆模式下可用
        en_orbit = self._mode == 'orbit'
        self.chk_tangent.setEnabled(en_orbit)
        # 起始方位角 & 顶底左右快捷按钮：只在圆模式可用
        self.spin_start_angle.setEnabled(en_orbit)
        for b in getattr(self, '_sa_btns', []):
            b.setEnabled(en_orbit)
        # ★ 字符角度：slide / orbit 都可用
        self.spin_obj_offset.setEnabled(en_slide)
        # ★ 反转只有勾选切线旋转时才可用
        en_rev = en_orbit and self.chk_tangent.isChecked()
        self.chk_reverse.setEnabled(en_rev)
        # ★ 三个按钮改为只读指示器，不能点击切换
        hl_active = ("QPushButton{background-color:#4a90d9;"
                     "color:#ffffff;font-weight:bold;"
                     "border:1px solid #2f6fb0;border-radius:3px;}")
        hl_inactive = ("QPushButton{background-color:#3a3a3a;"
                       "color:#777777;"
                       "border:1px solid #555555;border-radius:3px;}")
        for m, b in (('static', self.btn_preset_static),
                     ('slide', self.btn_preset_slide),
                     ('orbit', self.btn_preset_orbit)):
            b.setEnabled(False)
            b.setStyleSheet(hl_active if m == self._mode else hl_inactive)

    # ---------------- 参数变化 → 重新生成 ----------------
    def _on_param_changed(self, *args):
        # 参数改变只影响 values() 里合成的公式，不需要刷新输入框
        try:
            en_orbit = (self._mode == 'orbit')
            # 反转按钮
            en_rev = en_orbit and self.chk_tangent.isChecked()
            self.chk_reverse.setEnabled(en_rev)
            if not en_rev and self.chk_reverse.isChecked():
                self.chk_reverse.blockSignals(True)
                self.chk_reverse.setChecked(False)
                self.chk_reverse.blockSignals(False)
            # 起始方位角相关控件
            self.spin_start_angle.setEnabled(en_orbit)
            for b in getattr(self, '_sa_btns', []):
                b.setEnabled(en_orbit)
        except Exception:
            pass

    def _on_expr_edited(self):
        # 保留占位：编辑框已移除，此方法不再使用
        pass

    # ---------------- 表达式生成 ----------------
    def _regen_expr(self):
        # ★ 现在完整公式在 values() 里按参数动态合成
        #   输入框只显示"用户额外叠加"的内容，默认留空
        pass

    def _gen_slide(self):
        pass

    def _gen_slide_impl(self):
        pass

    def _gen_orbit(self):
        pass

    def _gen_orbit_impl(self):
        pass

    # ---------------- 初始化 ----------------
    def _load_current(self):
        try:
            self._load_current_impl()
        except RecursionError:
            self._mode = 'static'
            self._updating_expr = False
        except Exception:
            import traceback
            traceback.print_exc()
            self._mode = 'static'
            self._updating_expr = False

    def _load_current_impl(self):
        p = self.parent_obj

        # ★ 控制方式由父对象类型自动决定（按钮只是指示）
        if isinstance(p, HelperLine):
            self._mode = 'slide'
        elif isinstance(p, HelperCircle):
            self._mode = 'orbit'
        else:
            self._mode = 'static'

        # 恢复上次保存的参数
        saved_ctrl = getattr(self.child, '_bind_dialog_ctrl', None)
        saved_t0 = getattr(self.child, '_bind_dialog_t0', None)
        saved_t1 = getattr(self.child, '_bind_dialog_t1', None)
        saved_tan = getattr(self.child, '_bind_dialog_tangent', None)
        saved_rev = getattr(self.child, '_bind_dialog_reverse', None)
        saved_sa = getattr(self.child, '_bind_dialog_start_angle', None)
        saved_off = getattr(self.child, '_bind_dialog_obj_offset', None)
        if saved_ctrl is not None: self.edit_ctrl.setText(saved_ctrl)
        if saved_t0 is not None: self.spin_t0.setValue(float(saved_t0))
        if saved_t1 is not None: self.spin_t1.setValue(float(saved_t1))
        if saved_tan is not None: self.chk_tangent.setChecked(bool(saved_tan))
        if saved_rev is not None: self.chk_reverse.setChecked(bool(saved_rev))
        if saved_sa is not None: self.spin_start_angle.setValue(float(saved_sa))
        if saved_off is not None: self.spin_obj_offset.setValue(float(saved_off))

        self._update_ui_state()

    def _save_meta(self):
        """把当前模式参数保存到 child，下次打开可恢复"""
        try:
            self.child._bind_dialog_mode = self._mode
            self.child._bind_dialog_ctrl = self.edit_ctrl.text()
            self.child._bind_dialog_t0 = self.spin_t0.value()
            self.child._bind_dialog_t1 = self.spin_t1.value()
            self.child._bind_dialog_tangent = self.chk_tangent.isChecked()
            self.child._bind_dialog_reverse = self.chk_reverse.isChecked()
            self.child._bind_dialog_start_angle = self.spin_start_angle.value()
            self.child._bind_dialog_obj_offset = self.spin_obj_offset.value()
            # 用户额外叠加的 pos/vo/rotate 由属性面板统一管理，
            # 本对话框不再处理
        except Exception:
            pass

    def accept(self):
        # ★ 现在完整公式在 values() 里按参数动态合成，这里不需要兜底
        self._save_meta()
        super().accept()

    def _build_base_exprs(self):
        """按当前模式与参数生成基础 (dx, dy, ang) 表达式，
        不含用户在输入框里额外叠加的内容。"""
        p = self.parent_obj
        dx_base = u""
        dy_base = u""
        ang_base = u""
        if self._mode == 'slide' and isinstance(p, HelperLine):
            line_name = getattr(p, 'name', u'') or u''
            ctrl = self.edit_ctrl.text().strip() or u"Activate1"
            t0 = self.spin_t0.value()
            t1 = self.spin_t1.value()
            # ★ t0 是"起点"：ctrl=t0 时字符在线的起点
            #    t1 是"终点"：ctrl=t1 时字符在线的终点
            if abs(t1 - t0) < 1e-9:
                t_norm = u"0"
            else:
                t_norm = u"clamp(((%s)-(%s))/(%s),0,1)" % (
                    ctrl, _fmt(t0), _fmt(t1 - t0))
            half_norm = u"((%s)-0.5)" % t_norm
            if line_name:
                L_expr = (u"sqrt(({%s_X2}-{%s_X1})*({%s_X2}-{%s_X1})"
                          u"+({%s_Y2}-{%s_Y1})*({%s_Y2}-{%s_Y1}))"
                          % (line_name, line_name, line_name, line_name,
                             line_name, line_name, line_name, line_name))
                dx_base = u"%s*(%s)" % (half_norm, L_expr)
            else:
                try:
                    L = math.hypot(p.dx2() - p.dx1(), p.dy2() - p.dy1())
                except Exception:
                    L = 1.0
                if L < 1e-9: L = 1.0
                dx_base = u"%s*(%s)" % (half_norm, _fmt(L))
            dy_base = u"0"
            # ★ 字符角度也适用于 slide 模式：叠加到基础旋转上
            obj_offset = self.spin_obj_offset.value()
            if abs(obj_offset) > 1e-9:
                ang_base = _fmt(obj_offset)
            else:
                ang_base = u"0"
        elif self._mode == 'orbit' and isinstance(p, HelperCircle):
            R = p.dr()
            cname = getattr(p, 'name', u'') or u''
            ctrl = self.edit_ctrl.text().strip() or u"Activate1"
            t0 = self.spin_t0.value()
            t1 = self.spin_t1.value()
            start_angle = self.spin_start_angle.value()
            obj_offset = self.spin_obj_offset.value()
            use_tan = self.chk_tangent.isChecked()
            # ★ t0 是"起点"：ctrl=t0 时字符就在 start_angle 方向
            #    t1 是"终点"：ctrl=t1 时字符转过一圈
            #    不管 t0/t1 谁大谁小，都按 t0 → t1 的方向旋转
            if abs(t1 - t0) < 1e-9:
                t_norm = u"0"
            else:
                t_norm = u"clamp(((%s)-(%s))/(%s),0,1)" % (
                    ctrl, _fmt(t0), _fmt(t1 - t0))
            if abs(start_angle) < 1e-9:
                theta_expr = u"(%s)*360" % t_norm
            else:
                theta_expr = u"(%s)+(%s)*360" % (_fmt(start_angle), t_norm)
            # ★ 用辅助引用 {C1_R}，而不是硬编码 R
            #   这样用户改圆半径（或半径表达式）后，吸附元素立即跟随
            if cname:
                R_expr = u"{%s_R}" % cname
            else:
                R_expr = _fmt(R)
            dx_base = u"(-%s)*sin(%s)" % (R_expr, theta_expr)
            dy_base = u"(-%s)*cos(%s)" % (R_expr, theta_expr)
            use_reverse = self.chk_reverse.isChecked()
            if use_tan:
                if use_reverse:
                    ang_base = u"-((%s)+180)" % theta_expr
                else:
                    ang_base = u"(%s)+180" % theta_expr
            else:
                ang_base = u"0"
            # 字符角度叠加
            if abs(obj_offset) > 1e-9:
                if ang_base == u"0":
                    ang_base = _fmt(obj_offset)
                else:
                    ang_base = u"(%s)+(%s)" % (ang_base, _fmt(obj_offset))
        return dx_base, dy_base, ang_base

    def values(self):
        """返回 (dx_base, dy_base, ang_base) —— 只含吸附基础公式
        用户额外叠加的 pos/vo/rotate 由字符属性面板的
        custom_pos_expr / custom_vo_expr / custom_rot_expr 提供
        """
        dx_base, dy_base, ang_base = self._build_base_exprs()
        return (dx_base, dy_base, ang_base)


# ================================================================
#                  3D 目标控制 - 基础模块
# ================================================================

class _V3(object):
    """轻量级 3D 向量（东 / 北 / 上，单位米）"""
    __slots__ = ('x', 'y', 'z')

    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x = float(x); self.y = float(y); self.z = float(z)

    def copy(self):
        return _V3(self.x, self.y, self.z)

    def __add__(self, o): return _V3(self.x + o.x, self.y + o.y, self.z + o.z)
    def __sub__(self, o): return _V3(self.x - o.x, self.y - o.y, self.z - o.z)
    def __mul__(self, s): return _V3(self.x * s, self.y * s, self.z * s)
    def __truediv__(self, s): return _V3(self.x / s, self.y / s, self.z / s)
    def dot(self, o): return self.x * o.x + self.y * o.y + self.z * o.z

    def cross(self, o):
        return _V3(self.y * o.z - self.z * o.y,
                   self.z * o.x - self.x * o.z,
                   self.x * o.y - self.y * o.x)

    def length(self):
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def norm(self):
        L = self.length()
        if L < 1e-9:
            return _V3()
        return _V3(self.x / L, self.y / L, self.z / L)


def _heading_to_dir(heading_deg, elev_deg=0.0):
    """把 (Heading, Elevation) 转成单位方向向量（东/北/上）"""
    h = math.radians(heading_deg)
    e = math.radians(elev_deg)
    return _V3(math.cos(e) * math.sin(h),
               math.cos(e) * math.cos(h),
               math.sin(e))


def _body_frame(heading_deg, elev_deg, roll_deg=0.0):
    """返回机体本地坐标系三轴：(right, forward, up)，东/北/上坐标。
    ★ 用旋转矩阵组合避免万向节锁：俯仰接近 ±90° 时不会跳变。
    """
    h = math.radians(heading_deg)
    e = math.radians(elev_deg)
    r = math.radians(roll_deg)

    ch, sh = math.cos(h), math.sin(h)
    ce, se = math.cos(e), math.sin(e)

    # 基础姿态（roll=0）
    forward = _V3(ce * sh, ce * ch, se)
    right = _V3(ch, -sh, 0.0)
    up = _V3(-se * sh, -se * ch, ce)

    if abs(roll_deg) < 1e-9:
        return right, forward, up

    cr, sr = math.cos(r), math.sin(r)
    nx, ny, nz = forward.x, forward.y, forward.z

    def _rot(v):
        # Rodrigues 绕 forward 轴旋转（right/up 与 forward 正交）
        cx = ny * v.z - nz * v.y
        cy = nz * v.x - nx * v.z
        cz = nx * v.y - ny * v.x
        return _V3(v.x * cr + cx * sr,
                   v.y * cr + cy * sr,
                   v.z * cr + cz * sr)

    return _rot(right), forward, _rot(up)


class _OrbitCamera(object):
    """轨道相机：围绕注视点旋转 + 缩放"""
    def __init__(self):
        self.target = _V3(0.0, 0.0, 0.0)
        self.azimuth = 45.0     # 水平角（度）
        self.elevation = 45.0   # 俯仰角（度）
        self.distance = 400.0   # 距离注视点的距离（米）
        self.fov = 55.0         # 视场角

    def eye(self):
        """相机在世界坐标中的位置"""
        az = math.radians(self.azimuth)
        el = math.radians(self.elevation)
        d = self.distance
        return _V3(self.target.x + d * math.cos(el) * math.sin(az),
                   self.target.y + d * math.cos(el) * math.cos(az),
                   self.target.z + d * math.sin(el))

    def basis(self):
        """返回 (右, 上, 前) 三个基向量"""
        eye = self.eye()
        fwd = (self.target - eye).norm()
        world_up = _V3(0, 0, 1)
        right = fwd.cross(world_up).norm()
        if right.length() < 1e-6:
            right = _V3(1, 0, 0)
        up = right.cross(fwd).norm()
        return right, up, fwd

    def project(self, p, W, H):
        """世界坐标 → 屏幕坐标，返回 (sx, sy, depth)"""
        eye = self.eye()
        right, up, fwd = self.basis()
        rel = p - eye
        cx = rel.dot(right)
        cy = rel.dot(up)
        cz = rel.dot(fwd)
        if cz < 0.05:
            cz = 0.05
        f = (H / 2.0) / math.tan(math.radians(self.fov) / 2.0)
        sx = W / 2.0 + (cx / cz) * f
        sy = H / 2.0 - (cy / cz) * f
        return sx, sy, cz


class _SceneObj(object):
    """场景里的运动对象（主机体 或 目标）"""

    _id_seq = 0
    # 目标配色池：中等亮度、彼此易区分（避开纯黑/纯白）
    _palette = [
        QColor("#00c8ff"),  # 青蓝
        QColor("#ff5c5c"),  # 红
        QColor("#5cff7c"),  # 绿
        QColor("#ffd040"),  # 金
        QColor("#c060ff"),  # 紫
        QColor("#ff9040"),  # 橙
        QColor("#40ffd0"),  # 青绿
        QColor("#ff40c0"),  # 洋红
        QColor("#80ff40"),  # 黄绿
        QColor("#6080ff"),  # 蓝紫
    ]

    def __init__(self, name=u"", is_player=False):
        self.name = name
        self.is_player = is_player
        _SceneObj._id_seq += 1
        if is_player:
            self.color = QColor("#3090ff")   # 主机体固定蓝
        else:
            self.color = QColor(_SceneObj._palette[
                (_SceneObj._id_seq - 1) % len(_SceneObj._palette)])
        # 位置用相对坐标（东/北/上，相对主机体初始点，米）
        self.pos = _V3(0.0, 0.0, 0.0)
        # 姿态
        self.heading = 0.0      # 度，北=0，东=+90，西=-90
        self.elevation = 0.0    # 度，上=+，下=-
        self.roll = 0.0         # 度（仅主机体有意义）
        # 运动参数
        self.speed = 0.0        # m/s
        self.turn_rate = 0.0    # 度/秒（水平转向）
        # ★ 运动起始时间：pos 表示该时刻的位置（默认 0）
        self.t_start = 0.0
        # 显示开关
        self.visible = True
        self.selected = False
        # 轨迹（(t, pos) 列表）
        self.trail = []
        # 预计算的模拟轨迹（t → pos）—— 由 simulate() 填充
        self.sim_times = []
        self.sim_pos = []
        self.sim_heading = []
        self.sim_elevation = []

    def dir_vec(self):
        return _heading_to_dir(self.heading, self.elevation)

    def simulate(self, dt_total, dt_step):
        """从 t=0 起按固定时间步长积分，填充 sim_* 数组。
        简化模型：恒定速度 + 恒定转向率 + 恒定俯仰"""
        self.sim_times = []
        self.sim_pos = []
        self.sim_heading = []
        self.sim_elevation = []
        t = 0.0
        pos = self.pos.copy()
        hd = self.heading
        el = self.elevation
        n = max(1, int(round(dt_total / dt_step)) + 1)
        for i in range(n):
            self.sim_times.append(t)
            self.sim_pos.append(pos.copy())
            self.sim_heading.append(hd)
            self.sim_elevation.append(el)
            if i == n - 1:
                break
            d = _heading_to_dir(hd, el)
            pos = pos + d * (self.speed * dt_step)
            hd = hd + self.turn_rate * dt_step
            while hd > 180.0: hd -= 360.0
            while hd <= -180.0: hd += 360.0
            t += dt_step

    def sample_at(self, t):
        """按时间采样位置 + 姿态（线性插值）"""
        if not self.sim_times:
            return self.pos.copy(), self.heading, self.elevation
        ts = self.sim_times
        if t <= ts[0]:
            return self.sim_pos[0].copy(), self.sim_heading[0], self.sim_elevation[0]
        if t >= ts[-1]:
            return self.sim_pos[-1].copy(), self.sim_heading[-1], self.sim_elevation[-1]
        # 线性查找（时间步长均匀，直接算 index）
        dt = ts[1] - ts[0] if len(ts) > 1 else 1.0
        idx = int((t - ts[0]) / dt)
        idx = max(0, min(len(ts) - 2, idx))
        a = (t - ts[idx]) / dt
        p0 = self.sim_pos[idx]
        p1 = self.sim_pos[idx + 1]
        pos = _V3(p0.x + (p1.x - p0.x) * a,
                  p0.y + (p1.y - p0.y) * a,
                  p0.z + (p1.z - p0.z) * a)
        hd0 = self.sim_heading[idx]
        hd1 = self.sim_heading[idx + 1]
        hd = hd0 + (hd1 - hd0) * a
        el0 = self.sim_elevation[idx]
        el1 = self.sim_elevation[idx + 1]
        el = el0 + (el1 - el0) * a
        return pos, hd, el


class Track3DCanvas(QWidget):
    """3D 轨迹画布：网格 + 三轴 + 对象 + 轨迹 + 轨道相机"""

    objectsChanged = pyqtSignal()   # 对象增删 / 位置变化（供外部保存）
    cameraMoved = pyqtSignal()
    objectPicked = pyqtSignal(object)   # 鼠标按下选中某对象（主机体或目标）

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(480, 360)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.camera = _OrbitCamera()
        self.objects = []       # 包含主机体（第一个）
        self.current_time = 0.0
        self.duration = 60.0
        # 交互状态
        self._mode = None
        self._drag_start = None
        self._drag_obj = None
        self._drag_obj_start = None
        self._last_mouse = None
        # ★ 右键：单击 = 菜单，拖动 = 平移
        self._rbtn_start = None
        self._rbtn_moved = False
        # ★ 悬停到地面落点 / 本体的对象
        self._hover_ground_obj = None
        self._hover_body_obj = None
        # ★ 旋转 gizmo 状态
        self._rotate_obj = None
        self._rotate_axis = None
        self._rotate_hover_axis = None
        self._rotate_center_screen = QPointF()
        self._rotate_drag_start_angle = 0.0
        self._rotate_start_heading = 0.0
        self._rotate_start_elevation = 0.0
        self._rotate_start_roll = 0.0
        self._rotate_ring_cache = {}
        self._rotate_ring_normal_cache = {}
        self._rotate_ring_normal = None
        # 可选开关
        self.show_grid = True
        self.show_axes = True
        self.show_trail = True
        # ★ 锁定目标（从主机体到该目标画一条线）
        self.lock_target = None

    # ---------------- 数据 ----------------
    def add_object(self, obj):
        self.objects.append(obj)
        self.update()

    def remove_object(self, obj):
        if obj in self.objects:
            self.objects.remove(obj)
            self.update()

    def set_time(self, t):
        self.current_time = max(0.0, min(self.duration, float(t)))
        self.update()

    def set_duration(self, d):
        self.duration = max(0.5, float(d))
        if self.current_time > self.duration:
            self.current_time = self.duration
        self.update()

    def simulate_all(self):
        for obj in self.objects:
            obj.simulate(self.duration, 0.05)
        self.update()

    def _pan_camera(self, ddx, ddy):
        """相机平移：屏幕像素 → 世界偏移，与 _screen_to_plane_z 完全一致，
        保证"拖拽跟手"——相机平移和拖动对象/背景网格走同样的量。
        · 水平/垂直拖动都沿"屏幕方向"在水平面上的投影
        · target.z 保持不变，避免网格和视野错位
        """
        try:
            W, H = self.width(), self.height()
            cx, cy = W / 2.0, H / 2.0
            plane_z = self.camera.target.z

            # 用屏幕中心点 + 反向偏移点，求 ddx/ddy 对应的世界偏移
            p0 = self._screen_to_plane_z(cx, cy, plane_z)
            p1 = self._screen_to_plane_z(cx - ddx, cy - ddy, plane_z)

            if p0 is not None and p1 is not None:
                dx_w = p1.x - p0.x
                dy_w = p1.y - p0.y
                if not (math.isfinite(dx_w) and math.isfinite(dy_w)):
                    return
                LIM = 1000.0
                dx_w = max(-LIM, min(LIM, dx_w))
                dy_w = max(-LIM, min(LIM, dy_w))
            else:
                # 兜底：俯仰角接近 0° 时射线与平面几乎平行，
                # 用 焦距 / 距离 估算每像素世界单位
                right, up, _ = self.camera.basis()
                f = (H / 2.0) / math.tan(
                    math.radians(self.camera.fov) / 2.0)
                depth = max(1.0, (self.camera.target
                                  - self.camera.eye()).length())
                s = depth / max(1.0, f)

                r_h = _V3(right.x, right.y, 0.0)
                u_h = _V3(up.x, up.y, 0.0)
                r_h = r_h.norm() if r_h.length() > 1e-6 \
                    else _V3(1.0, 0.0, 0.0)
                u_h = u_h.norm() if u_h.length() > 1e-6 \
                    else _V3(0.0, 1.0, 0.0)

                d = r_h * (-ddx * s) + u_h * (ddy * s)
                dx_w, dy_w = d.x, d.y

            nx = self.camera.target.x + dx_w
            ny = self.camera.target.y + dy_w
            if not (math.isfinite(nx) and math.isfinite(ny)):
                return
            LIM = 1e6
            nx = max(-LIM, min(LIM, nx))
            ny = max(-LIM, min(LIM, ny))
            self.camera.target = _V3(nx, ny, self.camera.target.z)
        except Exception:
            pass

    def object_at_screen(self, sx, sy):
        """屏幕坐标 → 命中的对象（按深度从近到远遍历）"""
        W, H = self.width(), self.height()
        best = None
        best_depth = 1e18
        for obj in self.objects:
            if not obj.visible:
                continue
            pos, hd, el = obj.sample_at(self.current_time)
            px, py, pd = self.camera.project(pos, W, H)
            # ★ 主机体命中范围略大
            r = 16 if obj.is_player else 14
            if (px - sx) ** 2 + (py - sy) ** 2 <= r ** 2:
                if pd < best_depth:
                    best_depth = pd
                    best = obj
        return best

    def object_at_ground(self, sx, sy):
        """屏幕坐标 → 命中的对象地面落点（阈值更小，避免和本体冲突）"""
        W, H = self.width(), self.height()
        best = None
        best_d2 = 12.0 * 12.0
        for obj in self.objects:
            if not obj.visible:
                continue
            pos, hd, el = obj.sample_at(self.current_time)
            ground = _V3(pos.x, pos.y, 0.0)
            gx, gy, _ = self.camera.project(ground, W, H)
            d2 = (gx - sx) ** 2 + (gy - sy) ** 2
            if d2 < best_d2:
                best_d2 = d2
                best = obj
        return best

    def _screen_to_plane_z(self, sx, sy, z):
        """屏幕坐标 → 与 z = 常数 平面求交（世界坐标）"""
        try:
            W, H = self.width(), self.height()
            right, up, fwd = self.camera.basis()
            eye = self.camera.eye()
            f = (H / 2.0) / math.tan(math.radians(self.camera.fov) / 2.0)
            if not math.isfinite(f) or abs(f) < 1e-6:
                return None
            nx = (sx - W / 2.0) / f
            ny = -(sy - H / 2.0) / f
            rd = fwd + right * nx + up * ny
            if abs(rd.z) < 1e-4:
                return None
            t = (z - eye.z) / rd.z
            if t < 0 or t > 1e8:
                return None
            px = eye.x + rd.x * t
            py = eye.y + rd.y * t
            if not (math.isfinite(px) and math.isfinite(py)):
                return None
            LIM = 1e6
            if abs(px) > LIM or abs(py) > LIM:
                return None
            return _V3(px, py, z)
        except Exception:
            return None

    def _screen_to_ground(self, sx, sy):
        return self._screen_to_plane_z(sx, sy, 0.0)

    # ---------------- 鼠标 ----------------
    def mousePressEvent(self, e):
        x, y = e.pos().x(), e.pos().y()
        if e.button() == Qt.LeftButton:
            # ★ 旋转模式：左键点击环 → 开始拖动
            if self._rotate_obj is not None:
                axis = self._hit_rotate_ring(x, y)
                if axis is not None:
                    self._rotate_axis = axis
                    self._mode = 'rotate_gizmo'
                    pos, hd, el = self._rotate_obj.sample_at(self.current_time)
                    W, H = self.width(), self.height()
                    cx, cy, _ = self.camera.project(pos, W, H)
                    self._rotate_center_screen = QPointF(cx, cy)
                    self._rotate_drag_start_angle = math.atan2(y - cy, x - cx)
                    self._rotate_start_heading = self._rotate_obj.heading
                    self._rotate_start_elevation = self._rotate_obj.elevation
                    self._rotate_start_roll = getattr(
                        self._rotate_obj, 'roll', 0.0)
                    try:
                        self._rotate_ring_normal = \
                            self._rotate_ring_normal_cache.get(axis)
                    except Exception:
                        self._rotate_ring_normal = None
                    self.setCursor(Qt.ClosedHandCursor)
                    return
                # 点击非环区域 → 退出旋转模式
                self._exit_rotate_mode()
            shift = bool(e.modifiers() & Qt.ShiftModifier)
            obj_body = self.object_at_screen(x, y)
            obj_ground = self.object_at_ground(x, y)

            # ★ Shift + 左键 → 强制进入"垂直拖动高度"模式
            if shift:
                obj = obj_body if obj_body is not None else obj_ground
                if obj is not None:
                    self._mode = 'drag_obj'
                    self._drag_obj = obj
                    self._drag_start = (x, y)
                    self._drag_obj_start = obj.pos.copy()
                    self.setCursor(Qt.SizeVerCursor)
                    try:
                        self.objectPicked.emit(obj)
                    except Exception:
                        pass
                    return
                # Shift + 左键但没命中任何对象 → 什么都不做，避免误触
                return

            # 不按 Shift → 优先地面落点（水平拖动），其次本体
            if obj_ground is not None:
                self._mode = 'drag_ground'
                self._drag_obj = obj_ground
                self._drag_ground_g0 = self._screen_to_ground(x, y)
                self._drag_obj_start = obj_ground.pos.copy()
                self.setCursor(Qt.SizeAllCursor)
                try:
                    self.objectPicked.emit(obj_ground)
                except Exception:
                    pass
                return
            if obj_body is not None:
                self._mode = 'drag_obj'
                self._drag_obj = obj_body
                self._drag_start = (x, y)
                self._drag_obj_start = obj_body.pos.copy()
                self.setCursor(Qt.SizeAllCursor)
                try:
                    self.objectPicked.emit(obj_body)
                except Exception:
                    pass
                return

            # 空白 → 旋转相机
            self._mode = 'orbit'
            self._last_mouse = (x, y)
            self.setCursor(Qt.ClosedHandCursor)
        elif e.button() == Qt.RightButton:
            # ★ 记录按下起点，等待判断单击 / 拖动
            self._rbtn_start = (x, y)
            self._rbtn_moved = False
        elif e.button() == Qt.MiddleButton:
            self._mode = 'orbit'
            self._last_mouse = (x, y)
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        x, y = e.pos().x(), e.pos().y()

        # ★ 右键按住：先判断是否进入平移
        if self._rbtn_start is not None and (e.buttons() & Qt.RightButton):
            dx = x - self._rbtn_start[0]
            dy = y - self._rbtn_start[1]
            if not self._rbtn_moved and dx * dx + dy * dy > 25:
                self._rbtn_moved = True
                self._last_mouse = (x, y)
                self.setCursor(Qt.ClosedHandCursor)
            if self._rbtn_moved:
                ddx = x - self._last_mouse[0]
                ddy = y - self._last_mouse[1]
                self._last_mouse = (x, y)
                self._pan_camera(ddx, ddy)
                self.update()
                self.cameraMoved.emit()
            return

        # ★ 旋转 gizmo 拖动
        if self._mode == 'rotate_gizmo' and self._rotate_obj is not None:
            cx = self._rotate_center_screen.x()
            cy = self._rotate_center_screen.y()
            cur_angle = math.atan2(y - cy, x - cx)
            d_deg = math.degrees(cur_angle - self._rotate_drag_start_angle)
            while d_deg > 180.0:
                d_deg -= 360.0
            while d_deg < -180.0:
                d_deg += 360.0
            obj = self._rotate_obj

            # ★ 根据环法线与"物体→相机"方向判断翻转
            #   红/绿环：法向朝向相机 → 翻转
            #   蓝环   ：法向背向相机 → 翻转（与红/绿相反）
            n_ring = getattr(self, '_rotate_ring_normal', None)
            if n_ring is not None:
                try:
                    pos_cur, _, _ = obj.sample_at(self.current_time)
                    eye = self.camera.eye()
                    view_dir = (eye - pos_cur).norm()
                    dot = view_dir.dot(n_ring)
                    if self._rotate_axis == 'Z':
                        if dot < 0:
                            d_deg = -d_deg
                    else:
                        if dot > 0:
                            d_deg = -d_deg
                except Exception:
                    pass

            if self._rotate_axis == 'Z':
                # ★ 不归一化：无限累积（720, 1080...）
                obj.heading = self._rotate_start_heading + d_deg
            elif self._rotate_axis == 'X':
                # ★ 不 clamp：允许俯仰翻过 ±90，也可以一直累积
                obj.elevation = self._rotate_start_elevation + d_deg
            elif self._rotate_axis == 'Y':
                if getattr(obj, 'is_player', False):
                    obj.roll = self._rotate_start_roll + d_deg
            self.objectsChanged.emit()
            self.update()
            return


        if self._mode in ('orbit', 'pan') and self._last_mouse is not None:
            dx = x - self._last_mouse[0]
            dy = y - self._last_mouse[1]
            self._last_mouse = (x, y)
            if self._mode == 'orbit':
                self.camera.azimuth += dx * 0.15
                self.camera.elevation = max(-89.0, min(89.0,
                                                       self.camera.elevation + dy * 0.15))
            else:
                self._pan_camera(dx, dy)
            self.update()
            self.cameraMoved.emit()
        elif self._mode == 'drag_obj' and self._drag_obj is not None:
            if e.modifiers() & Qt.ShiftModifier:
                dy = y - self._drag_start[1]
                # ★ 用"水平距离 + 相机距离保底"估算参考深度，
                #   避免相机贴近网格平面时 depth≈0 → 拖动失效
                eye = self.camera.eye()
                dxh = self._drag_obj_start.x - eye.x
                dyh = self._drag_obj_start.y - eye.y
                horiz = math.hypot(dxh, dyh)
                ref = max(horiz, self.camera.distance * 0.5, 20.0)
                f = (self.height() / 2.0) / math.tan(
                    math.radians(self.camera.fov) / 2.0)
                dz = -dy * (ref / f)
                self._drag_obj.pos = _V3(
                    self._drag_obj_start.x,
                    self._drag_obj_start.y,
                    max(0.0, self._drag_obj_start.z + dz))
            else:
                p = self._screen_to_plane_z(x, y, self._drag_obj_start.z)
                p0 = self._screen_to_plane_z(
                    self._drag_start[0], self._drag_start[1],
                    self._drag_obj_start.z)
                if p is not None and p0 is not None:
                    delta = p - p0
                    self._drag_obj.pos = _V3(
                        self._drag_obj_start.x + delta.x,
                        self._drag_obj_start.y + delta.y,
                        self._drag_obj_start.z)
            self.objectsChanged.emit()
            self.update()
        elif self._mode == 'drag_ground' and self._drag_obj is not None:
            g = self._screen_to_ground(x, y)
            g0 = getattr(self, '_drag_ground_g0', None)
            if g is not None and g0 is not None:
                delta = g - g0
                self._drag_obj.pos = _V3(
                    self._drag_obj_start.x + delta.x,
                    self._drag_obj_start.y + delta.y,
                    self._drag_obj_start.z)
                self.objectsChanged.emit()
                self.update()

        # ★ 无按键：旋转 gizmo 悬停高亮
        if (not e.buttons()) and self._rotate_obj is not None:
            axis = self._hit_rotate_ring(x, y)
            if axis != self._rotate_hover_axis:
                self._rotate_hover_axis = axis
                if axis is not None:
                    self.setCursor(Qt.OpenHandCursor)
                else:
                    self.setCursor(Qt.ArrowCursor)
                self.update()

        else:
            # ★ 无键按下：检测悬停到地面落点 / 本体 → 变色 + 提示可拖动
            if not e.buttons():
                g_obj = self.object_at_ground(x, y)
                b_obj = self.object_at_screen(x, y)
                changed = False
                if g_obj is not self._hover_ground_obj:
                    self._hover_ground_obj = g_obj
                    changed = True
                if b_obj is not self._hover_body_obj:
                    self._hover_body_obj = b_obj
                    changed = True
                if changed:
                    if b_obj is not None or g_obj is not None:
                        self.setCursor(Qt.PointingHandCursor)
                    else:
                        self.setCursor(Qt.ArrowCursor)
                    self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.RightButton:
            # ★ 清掉起点；保留 _rbtn_moved 供 contextMenuEvent 判断
            self._rbtn_start = None
            self._last_mouse = None
            if self._rbtn_moved:
                self.setCursor(Qt.ArrowCursor)
                e.accept()
                return
            # 单击 → 让 contextMenuEvent 正常触发
            return
        if self._mode == 'rotate_gizmo':
            self._rotate_axis = None
            self.setCursor(Qt.OpenHandCursor)
            self._mode = None
            self.objectsChanged.emit()
            self.update()
            return
        self._mode = None
        self._drag_obj = None
        self.setCursor(Qt.ArrowCursor)

    def contextMenuEvent(self, e):
        # ★ 如果是拖动结束 → 忽略菜单
        if self._rbtn_moved:
            self._rbtn_moved = False
            e.accept()
            return
        self._rbtn_moved = False

        # 检测右键位置命中的对象
        hit = self.object_at_screen(e.pos().x(), e.pos().y())
        if hit is None:
            hit = self.object_at_ground(e.pos().x(), e.pos().y())

        is_target = (hit is not None) and (not getattr(hit, 'is_player', False))

        # ★ 右键目标是目标 → 通知外部把左侧列表切过去
        if is_target:
            try:
                self.objectPicked.emit(hit)
            except Exception:
                pass

        m = QMenu(self)

        # ★ 第一行：定位到 —— 命中目标就定位到目标，否则定位到主机体
        if is_target:
            act_focus = m.addAction(
                _L(u"定位到目标 [%s]", u"Focus on [%s]") % hit.name)
            act_focus.triggered.connect(
                lambda c=False, o=hit: self.focus_object(o))
        else:
            act_focus = m.addAction(
                _L(u"定位到主机体", u"Focus on Player"))
            act_focus.triggered.connect(self.focus_player)

        if hit is not None:
            m.addSeparator()
            # ★ 旋转模式入口
            if self._rotate_obj is hit:
                act_rot = m.addAction(
                    _L(u"✕ 退出旋转模式", u"✕ Exit Rotate Mode"))
                act_rot.triggered.connect(self._exit_rotate_mode)
            else:
                act_rot = m.addAction(
                    _L(u"⟳ 旋转模式", u"⟳ Rotate Mode"))
                act_rot.triggered.connect(
                    lambda c=False, o=hit: self._enter_rotate_mode(o))

        if is_target:
            act_remove = m.addAction(
                _L(u"删除目标 [%s]", u"Delete [%s]") % hit.name)
            act_remove.triggered.connect(
                lambda c=False, o=hit: self._request_remove(o))

        m.exec_(e.globalPos())

    def wheelEvent(self, e):
        d = e.angleDelta().y()
        if d == 0:
            return
        # ★ Shift + 滚轮：调整摄像机（注视点）高度（每档 5 米）
        if e.modifiers() & Qt.ShiftModifier:
            dz = 5.0 if d > 0 else -5.0
            new_z = self.camera.target.z + dz
            # 不做下限限制（允许贴地/略微负值），只做合理上限防溢出
            new_z = max(-100000.0, min(100000.0, new_z))
            if abs(new_z - self.camera.target.z) > 1e-9:
                self.camera.target = _V3(
                    self.camera.target.x,
                    self.camera.target.y,
                    new_z)
                self.update()
                self.cameraMoved.emit()
            e.accept()
            return
        # 普通滚轮：缩放
        factor = 0.85 if d > 0 else 1.0 / 0.85
        self.camera.distance = max(2.0, min(500000.0,
            self.camera.distance * factor))
        self.update()
        self.cameraMoved.emit()

    def _request_remove(self, obj):
        # 简单直接删除；上层对话框会同步列表
        self.remove_object(obj)
        self.objectsChanged.emit()

    def focus_player(self):
        for o in self.objects:
            if o.is_player:
                self.focus_object(o)
                return

    def focus_object(self, obj):
        pos, _, _ = obj.sample_at(self.current_time)
        self.camera.target = pos.copy()
        self.camera.distance = 200.0
        self.update()
        self.cameraMoved.emit()

    # ============================================================
    #                  旋转 Gizmo
    # ============================================================
    def _enter_rotate_mode(self, obj):
        self._rotate_obj = obj
        self._rotate_axis = None
        self._rotate_hover_axis = None
        self._rotate_ring_cache = {}
        self.setCursor(Qt.OpenHandCursor)
        self.update()

    def _exit_rotate_mode(self):
        self._rotate_obj = None
        self._rotate_axis = None
        self._rotate_hover_axis = None
        self._rotate_ring_cache = {}
        self.setCursor(Qt.ArrowCursor)
        self.update()

    def _hit_rotate_ring(self, x, y):
        if not self._rotate_ring_cache:
            return None
        best = None
        best_d2 = 12.0 * 12.0
        for name, pts in self._rotate_ring_cache.items():
            for sx, sy in pts:
                d2 = (sx - x) ** 2 + (sy - y) ** 2
                if d2 < best_d2:
                    best_d2 = d2
                    best = name
        return best

    def _draw_rotate_gizmo(self, p, W, H):
        obj = self._rotate_obj
        if obj is None or not obj.visible:
            return
        pos, hd, el = obj.sample_at(self.current_time)
        eye = self.camera.eye()
        depth = (pos - eye).length()
        if depth < 1e-6:
            return
        f = (H / 2.0) / math.tan(math.radians(self.camera.fov) / 2.0)
        world_radius = max(0.5, depth * 0.30)

        # 环的轴：红环只随 heading（无 roll 影响），绿环随 heading + elevation
        h_rad = math.radians(hd)
        e_rad = math.radians(el)
        ch, sh = math.cos(h_rad), math.sin(h_rad)
        ce, se = math.cos(e_rad), math.sin(e_rad)
        right_ring = _V3(ch, -sh, 0.0)          # 只随 heading
        fwd_ring = _V3(ce * sh, ce * ch, se)    # heading + elevation

        is_player = bool(getattr(obj, 'is_player', False))

        if is_player:
            rings = [
                ('Z', _V3(0.0, 0.0, 1.0), QColor(90, 150, 255)),
                ('X', right_ring, QColor(255, 90, 90)),
                ('Y', fwd_ring, QColor(90, 220, 90)),
            ]
        else:
            rings = [
                ('Z', _V3(0.0, 0.0, 1.0), QColor(90, 150, 255)),
                ('X', right_ring, QColor(255, 90, 90)),
            ]

        self._rotate_ring_cache = {}
        self._rotate_ring_normal_cache = {}
        N = 72
        for name, n, col in rings:
            if n is None or n.length() < 1e-6:
                continue
            ref = _V3(0.0, 0.0, 1.0)
            if abs(n.dot(ref)) > 0.9:
                ref = _V3(1.0, 0.0, 0.0)
            u = n.cross(ref).norm()
            v = n.cross(u).norm()
            if u.length() < 1e-6 or v.length() < 1e-6:
                continue
            pts_screen = []
            for i in range(N + 1):
                t = i / N * 2.0 * math.pi
                wp = pos + u * (world_radius * math.cos(t)) \
                     + v * (world_radius * math.sin(t))
                sx, sy, _ = self.camera.project(wp, W, H)
                if not (math.isfinite(sx) and math.isfinite(sy)):
                    continue
                pts_screen.append((sx, sy))
            if len(pts_screen) < 4:
                continue
            self._rotate_ring_cache[name] = pts_screen
            self._rotate_ring_normal_cache[name] = n.copy()

            hovered = (self._rotate_hover_axis == name)
            active = (self._rotate_axis == name)
            pen = QPen(col, 4 if active else (3 if hovered else 2))
            pen.setCosmetic(True)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            path = QPainterPath()
            path.moveTo(pts_screen[0][0], pts_screen[0][1])
            for sx, sy in pts_screen[1:]:
                path.lineTo(sx, sy)
            p.drawPath(path)

        # 中心小球
        cx, cy, _ = self.camera.project(pos, W, H)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(255, 255, 255, 200)))
        p.drawEllipse(QPointF(cx, cy), 5, 5)

        # 提示文字
        p.setPen(QColor(200, 210, 225))
        fnt = p.font();
        fnt.setPointSize(8);
        p.setFont(fnt)
        tip = (_L(u"蓝=航向  红=俯仰  绿=滚转",
                  u"B=Heading  R=Pitch  G=Roll")
               if is_player else
               _L(u"蓝=航向  红=俯仰",
                  u"B=Heading  R=Pitch"))
        p.drawText(QRectF(cx - 90, cy + world_radius * 0.5, 180, 16),
                   Qt.AlignCenter, tip)

    # ---------------- 渲染 ----------------
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.fillRect(self.rect(), QColor("#1e2024"))
        W, H = self.width(), self.height()

        # 1) 地面网格
        if self.show_grid:
            self._draw_ground_grid(p, W, H)
        # 2) 三轴
        if self.show_axes:
            self._draw_axes(p, W, H)
        # 3) 轨迹
        if self.show_trail:
            for obj in self.objects:
                self._draw_trail(p, W, H, obj)
        # 4) 对象（按深度从远到近画）
        draw_list = []
        for obj in self.objects:
            if not obj.visible:
                continue
            pos, hd, el = obj.sample_at(self.current_time)
            px, py, pd = self.camera.project(pos, W, H)
            draw_list.append((pd, obj, pos, hd, el, px, py))
        draw_list.sort(key=lambda x: -x[0])
        for _, obj, pos, hd, el, px, py in draw_list:
            if obj.is_player:
                self._draw_player(p, obj, pos, hd, el, px, py, W, H)
            else:
                self._draw_target(p, obj, pos, hd, el, px, py, W, H)

        # ★ 锁定线
        try:
            self._draw_lock_line(p, W, H)
        except Exception:
            pass

        # ★ 旋转 gizmo
        if self._rotate_obj is not None:
            try:
                self._draw_rotate_gizmo(p, W, H)
            except Exception:
                pass

        # 底部提示
        p.setPen(QColor(120, 130, 140))
        f = p.font(); f.setPointSize(9); p.setFont(f)
        hint = _L(
            u"滚轮：缩放 / 拖动旋转 | Shift+滚轮：视角高度 | "
            u"右键：视角平移 | Shift+左键：垂直移动目标",
            u"Wheel: zoom / drag to orbit | Shift+Wheel: camera height | "
            u"RMB: pan | Shift+LMB: vertical move")
        p.drawText(10, H - 10, hint)

    def _draw_ground_grid(self, p, W, H):
        """地面网格：以相机注视点为中心，随相机距离调整步长。
        带坐标数值标签（跟随相机目标点，自动缩放密度）。
        """
        right, up, fwd = self.camera.basis()
        eye = self.camera.eye()
        f = (H / 2.0) / math.tan(math.radians(self.camera.fov) / 2.0)
        if f <= 1e-6:
            return
        px_per_m = f / max(1.0, self.camera.distance)
        raw = 60.0 / max(1e-6, px_per_m)
        if raw <= 0:
            return
        exp = math.floor(math.log10(raw))
        base = 10 ** exp
        step = base
        for m in (1, 2, 5, 10):
            if base * m >= raw:
                step = base * m
                break
        else:
            step = base * 10

        cx = self.camera.target.x
        cy = self.camera.target.y
        span = self.camera.distance * 2.0

        i0 = int(math.floor((cx - span) / step))
        i1 = int(math.ceil((cx + span) / step))
        j0 = int(math.floor((cy - span) / step))
        j1 = int(math.ceil((cy + span) / step))
        if (i1 - i0) > 300 or (j1 - j0) > 300:
            return

        NEAR = 0.5
        PAD = 80
        HARD_LIMIT = 1e9

        ex, ey, ez = eye.x, eye.y, eye.z
        fx, fy, fz = fwd.x, fwd.y, fwd.z
        rX, rY, rZ = right.x, right.y, right.z
        uX, uY, uZ = up.x, up.y, up.z

        xmin, ymin = -PAD, -PAD
        xmax, ymax = W + PAD, H + PAD

        # X 方向网格（垂直的线，固定 X，沿 Y 延伸）→ 偏冷/偏蓝，稍亮
        pen_minor_x = QPen(QColor(62, 78, 96))
        pen_minor_x.setCosmetic(True)
        pen_major_x = QPen(QColor(105, 140, 175))
        pen_major_x.setCosmetic(True)
        # Y 方向网格（水平的线，固定 Y，沿 X 延伸）→ 偏暗/偏灰
        pen_minor_y = QPen(QColor(56, 58, 62))
        pen_minor_y.setCosmetic(True)
        pen_major_y = QPen(QColor(92, 94, 98))
        pen_major_y.setCosmetic(True)

        def project_pt(wx, wy):
            dxw = wx - ex;
            dyw = wy - ey;
            dzw = -ez
            cz = dxw * fx + dyw * fy + dzw * fz
            if cz < 1e-9:
                return None
            cxs = dxw * rX + dyw * rY + dzw * rZ
            cys = dxw * uX + dyw * uY + dzw * uZ
            sx = W / 2.0 + cxs / cz * f
            sy = H / 2.0 - cys / cz * f
            if not (math.isfinite(sx) and math.isfinite(sy)):
                return None
            return sx, sy

        def draw_segment(wx1, wy1, wx2, wy2, pen):
            dxw1 = wx1 - ex;
            dyw1 = wy1 - ey;
            dzw1 = -ez
            dxw2 = wx2 - ex;
            dyw2 = wy2 - ey;
            dzw2 = -ez
            cz1 = dxw1 * fx + dyw1 * fy + dzw1 * fz
            cz2 = dxw2 * fx + dyw2 * fy + dzw2 * fz

            if cz1 < NEAR and cz2 < NEAR:
                return
            if cz1 < NEAR:
                den = cz2 - cz1
                if den <= 1e-9:
                    return
                t = (NEAR - cz1) / den
                wx1 += (wx2 - wx1) * t
                wy1 += (wy2 - wy1) * t
                dxw1 = wx1 - ex;
                dyw1 = wy1 - ey;
                dzw1 = -ez
                cz1 = NEAR
            elif cz2 < NEAR:
                den = cz1 - cz2
                if den <= 1e-9:
                    return
                t = (NEAR - cz2) / den
                wx2 += (wx1 - wx2) * t
                wy2 += (wy1 - wy2) * t
                dxw2 = wx2 - ex;
                dyw2 = wy2 - ey;
                dzw2 = -ez
                cz2 = NEAR

            cxs1 = dxw1 * rX + dyw1 * rY + dzw1 * rZ
            cys1 = dxw1 * uX + dyw1 * uY + dzw1 * uZ
            cxs2 = dxw2 * rX + dyw2 * rY + dzw2 * rZ
            cys2 = dxw2 * uX + dyw2 * uY + dzw2 * uZ

            if cz1 < 1e-9 or cz2 < 1e-9:
                return

            x1 = W / 2.0 + cxs1 / cz1 * f
            y1 = H / 2.0 - cys1 / cz1 * f
            x2 = W / 2.0 + cxs2 / cz2 * f
            y2 = H / 2.0 - cys2 / cz2 * f

            if not (math.isfinite(x1) and math.isfinite(y1) and
                    math.isfinite(x2) and math.isfinite(y2)):
                return
            if abs(x1) > HARD_LIMIT or abs(y1) > HARD_LIMIT or \
                    abs(x2) > HARD_LIMIT or abs(y2) > HARD_LIMIT:
                return
            if (x1 < xmin and x2 < xmin) or (x1 > xmax and x2 > xmax) or \
                    (y1 < ymin and y2 < ymin) or (y1 > ymax and y2 > ymax):
                return

            ddx = x2 - x1
            ddy = y2 - y1
            u1, u2 = 0.0, 1.0
            for pi, qi in ((-ddx, x1 - xmin), (ddx, xmax - x1),
                           (-ddy, y1 - ymin), (ddy, ymax - y1)):
                if abs(pi) < 1e-12:
                    if qi < 0:
                        return
                else:
                    t = qi / pi
                    if pi < 0:
                        if t > u1: u1 = t
                    else:
                        if t < u2: u2 = t
            if u1 > u2:
                return

            fx1 = x1 + u1 * ddx
            fy1 = y1 + u1 * ddy
            fx2 = x1 + u2 * ddx
            fy2 = y1 + u2 * ddy

            if not (math.isfinite(fx1) and math.isfinite(fy1) and
                    math.isfinite(fx2) and math.isfinite(fy2)):
                return

            p.setPen(pen)
            p.drawLine(QLineF(fx1, fy1, fx2, fy2))

        # 沿 y 方向的线（固定 x）→ X 系列颜色
        for i in range(i0, i1 + 1):
            x = i * step
            pen = pen_major_x if i == 0 else pen_minor_x
            draw_segment(x, j0 * step, x, j1 * step, pen)

        # 沿 x 方向的线（固定 y）→ Y 系列颜色
        for j in range(j0, j1 + 1):
            y = j * step
            pen = pen_major_y if j == 0 else pen_minor_y
            draw_segment(i0 * step, y, i1 * step, y, pen)

        # ---------------- 坐标数值标签（左侧 + 底部，按方位角自动对调） ----------------
        px_per_step = max(0.1, step * px_per_m)
        label_stride = max(1, int(math.ceil(70.0 / px_per_step)))
        label_stride = min(label_stride, 200)

        if step >= 1:
            dec = 0
        elif step >= 0.1:
            dec = 1
        elif step >= 0.01:
            dec = 2
        elif step >= 0.001:
            dec = 3
        else:
            dec = 4

        def fmt_c(v):
            if abs(v) < 1e-12:
                return "0"
            s = "%.*f" % (dec, v)
            if '.' in s:
                s = s.rstrip('0').rstrip('.')
            if s in ('-0', ''):
                s = '0'
            return s

        label_font = QFont("Consolas")
        label_font.setPointSize(8)
        p.setFont(label_font)
        fm_lbl = QFontMetricsF(label_font)

        # X 系列颜色（冷蓝，对应垂直网格线）
        x_border_col = QColor(105, 140, 175)
        x_fg_col = QColor(180, 210, 240)
        # Y 系列颜色（暖灰，对应水平网格线）
        y_border_col = QColor(120, 122, 126)
        y_fg_col = QColor(228, 224, 218)

        def draw_label_at(sx, sy, text, kind='x'):
            tw = fm_lbl.horizontalAdvance(text)
            th = fm_lbl.height()
            rect = QRectF(sx - tw / 2.0 - 3,
                          sy - th / 2.0 - 1,
                          tw + 6, th + 2)
            if kind == 'x':
                p.setPen(QPen(x_border_col, 1))
                fg = x_fg_col
            else:
                p.setPen(QPen(y_border_col, 1))
                fg = y_fg_col
            p.setBrush(QBrush(QColor(20, 22, 28, 220)))
            p.drawRoundedRect(rect, 2, 2)
            p.setPen(QPen(fg))
            p.drawText(QPointF(sx - tw / 2.0,
                               sy + fm_lbl.ascent() / 2.0 - 1),
                       text)
            p.setBrush(Qt.NoBrush)

        # 沿投影线段采样，找它与屏幕边缘线的交点
        def find_edge_hit(wx1, wy1, wx2, wy2, edge_val, is_horizontal):
            NS = 96
            prev = None
            for k in range(NS + 1):
                t = k / NS
                wx = wx1 + (wx2 - wx1) * t
                wy = wy1 + (wy2 - wy1) * t
                pt = project_pt(wx, wy)
                if pt is None:
                    prev = None
                    continue
                if prev is not None:
                    if is_horizontal:
                        y1p, y2p = prev[1], pt[1]
                        if (y1p - edge_val) * (y2p - edge_val) <= 0:
                            if abs(y2p - y1p) > 1e-6:
                                tt = (edge_val - y1p) / (y2p - y1p)
                            else:
                                tt = 0.5
                            cx = prev[0] + tt * (pt[0] - prev[0])
                            return (cx, edge_val)
                    else:
                        x1p, x2p = prev[0], pt[0]
                        if (x1p - edge_val) * (x2p - edge_val) <= 0:
                            if abs(x2p - x1p) > 1e-6:
                                tt = (edge_val - x1p) / (x2p - x1p)
                            else:
                                tt = 0.5
                            cy = prev[1] + tt * (pt[1] - prev[1])
                            return (edge_val, cy)
                prev = pt
            return None

        # ★ 按方位角象限决定左右分配：
        #   象限 1 (90,180) 和 3 (270,360) —— 保持原样（用户反馈好）
        #   象限 0 (0,90) 和 2 (180,270)   —— 镜像对调
        az_full = self.camera.azimuth % 360.0
        az_mod = az_full % 90.0
        quadrant = int(az_full // 90.0)
        if quadrant in (1, 3):
            if az_mod < 45.0:
                left_axis, bottom_axis = 'x', 'y'
            else:
                left_axis, bottom_axis = 'y', 'x'
        else:
            if az_mod < 45.0:
                left_axis, bottom_axis = 'y', 'x'
            else:
                left_axis, bottom_axis = 'x', 'y'

        LEFT_PAD = 30
        # ★ 相机位于网格平面下方（z<0）时，把"底部"标签翻到画面顶部
        if self.camera.eye().z < 0.0:
            BOTTOM_PAD = 30
        else:
            BOTTOM_PAD = H - 30

        # ---- 左侧 ----
        if left_axis == 'x':
            for i in range(i0, i1 + 1):
                if i == 0 or i % label_stride != 0:
                    continue
                wx = i * step
                hit = find_edge_hit(wx, j0 * step, wx, j1 * step,
                                    LEFT_PAD, False)
                if hit is None:
                    continue
                sx, sy = hit
                if sy < 24 or sy > H - 24:
                    continue
                draw_label_at(sx, sy, fmt_c(wx), 'x')
        else:
            for j in range(j0, j1 + 1):
                if j == 0 or j % label_stride != 0:
                    continue
                wy = j * step
                hit = find_edge_hit(i0 * step, wy, i1 * step, wy,
                                    LEFT_PAD, False)
                if hit is None:
                    continue
                sx, sy = hit
                if sy < 24 or sy > H - 24:
                    continue
                draw_label_at(sx, sy, fmt_c(wy), 'y')

        # ---- 底部 ----
        if bottom_axis == 'x':
            for i in range(i0, i1 + 1):
                if i == 0 or i % label_stride != 0:
                    continue
                wx = i * step
                hit = find_edge_hit(wx, j0 * step, wx, j1 * step,
                                    BOTTOM_PAD, True)
                if hit is None:
                    continue
                sx, sy = hit
                if sx < 24 or sx > W - 24:
                    continue
                draw_label_at(sx, sy, fmt_c(wx), 'x')
        else:
            for j in range(j0, j1 + 1):
                if j == 0 or j % label_stride != 0:
                    continue
                wy = j * step
                hit = find_edge_hit(i0 * step, wy, i1 * step, wy,
                                    BOTTOM_PAD, True)
                if hit is None:
                    continue
                sx, sy = hit
                if sx < 24 or sx > W - 24:
                    continue
                draw_label_at(sx, sy, fmt_c(wy), 'y')

        # ---- 左侧原点 "0" ----
        if left_axis == 'x':
            origin_hit = find_edge_hit(0.0, j0 * step, 0.0, j1 * step,
                                       LEFT_PAD, False)
            origin_kind = 'x'
        else:
            origin_hit = find_edge_hit(i0 * step, 0.0, i1 * step, 0.0,
                                       LEFT_PAD, False)
            origin_kind = 'y'
        if origin_hit is not None:
            sx, sy = origin_hit
            if 24 <= sy <= H - 24:
                draw_label_at(sx, sy, "0", origin_kind)

        # ---- 底部原点 "0" ----
        if bottom_axis == 'x':
            origin_hit = find_edge_hit(0.0, j0 * step, 0.0, j1 * step,
                                       BOTTOM_PAD, True)
            origin_kind = 'x'
        else:
            origin_hit = find_edge_hit(i0 * step, 0.0, i1 * step, 0.0,
                                       BOTTOM_PAD, True)
            origin_kind = 'y'
        if origin_hit is not None:
            sx, sy = origin_hit
            if 24 <= sx <= W - 24:
                draw_label_at(sx, sy, "0", origin_kind)

        # ---- 右侧（与底部相同：同一轴、同色） ----
        RIGHT_PAD = W - 30
        if bottom_axis == 'x':
            for i in range(i0, i1 + 1):
                if i % label_stride != 0:
                    continue
                wx = i * step
                hit = find_edge_hit(wx, j0 * step, wx, j1 * step,
                                    RIGHT_PAD, False)
                if hit is None:
                    continue
                sx, sy = hit
                if sy < 24 or sy > H - 24:
                    continue
                draw_label_at(sx, sy, fmt_c(wx), 'x')
        else:
            for j in range(j0, j1 + 1):
                if j % label_stride != 0:
                    continue
                wy = j * step
                hit = find_edge_hit(i0 * step, wy, i1 * step, wy,
                                    RIGHT_PAD, False)
                if hit is None:
                    continue
                sx, sy = hit
                if sy < 24 or sy > H - 24:
                    continue
                draw_label_at(sx, sy, fmt_c(wy), 'y')

    def _draw_axes(self, p, W, H):
        """三轴：东=红、北=绿、上=蓝"""
        L = 50.0  # 箭头长度（米）
        o = self.camera.project(_V3(0, 0, 0), W, H)
        for (v, color, label) in (
                (_V3(L, 0, 0), QColor("#ff6060"), "E"),
                (_V3(0, L, 0), QColor("#60ff60"), "N"),
                (_V3(0, 0, L), QColor("#6090ff"), "U")):
            a = self.camera.project(v, W, H)
            p.setPen(QPen(color, 1.6))
            p.drawLine(int(o[0]), int(o[1]), int(a[0]), int(a[1]))
            p.drawText(int(a[0]) + 3, int(a[1]) - 3, label)

    def _draw_trail(self, p, W, H, obj):
        if len(obj.sim_times) < 2:
            return
        # 只画当前时间之前的轨迹
        t_end = self.current_time
        path = QPainterPath()
        started = False
        # 抽样步长：最多画 400 段，避免太密
        N = len(obj.sim_times)
        step = max(1, N // 400)
        first = True
        for i in range(0, N, step):
            t = obj.sim_times[i]
            if t > t_end:
                break
            pos = obj.sim_pos[i]
            px, py, _ = self.camera.project(pos, W, H)
            if first:
                path.moveTo(px, py)
                first = False
            else:
                path.lineTo(px, py)
        col = QColor(obj.color)
        col.setAlpha(200)
        pen = QPen(col, 1.6)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

    def _draw_target(self, p, obj, pos, hd, el, px, py, W, H):
        """目标：锥形（底部中点 = pos）"""
        hovered_body = (obj is self._hover_body_obj)
        hovered_ground = (obj is self._hover_ground_obj) or \
                         (obj is self._drag_obj and self._mode == 'drag_ground')
        col = QColor(obj.color)
        if hovered_body or hovered_ground:
            col = col.lighter(160)

        # ★ 垂线：从坐标点向下延伸到地面，并在地面画一个落点
        if pos.z > 1e-3:
            ground = _V3(pos.x, pos.y, 0.0)
            a = self.camera.project(pos, W, H)
            b = self.camera.project(ground, W, H)
            hovered = hovered_body or hovered_ground
            pen = QPen(QColor(col.red(), col.green(), col.blue(), 130), 1.0)
            pen.setStyle(Qt.DashLine)
            pen.setCosmetic(True)
            p.setPen(pen); p.setBrush(Qt.NoBrush)
            p.drawLine(QPointF(a[0], a[1]), QPointF(b[0], b[1]))
            p.setPen(Qt.NoPen)
            if hovered:
                dot_col = QColor(255, 255, 255, 240)
                r = 4.5
            else:
                dot_col = QColor(col.red(), col.green(), col.blue(), 200)
                r = 3.0
            p.setBrush(QBrush(dot_col))
            p.drawEllipse(QPointF(b[0], b[1]), r, r)

        # 锥体尺寸：随相机距离轻微缩放，保证可见
        depth = (pos - self.camera.eye()).length()
        scale = max(0.6, min(3.0, depth / 400.0))
        base_r = 6.0 * scale      # 底圆半径（米）
        height = 18.0 * scale     # 高

        # 计算锥体轴向（heading/elevation 方向）
        axis = _heading_to_dir(hd, el)
        # 底圆心 = pos + axis * height
        tip = pos + axis * height
        base_center = pos.copy()

        # 底圆：在垂直于 axis 的平面上取 3 个方向点，画一个椭圆多边形
        up_ref = _V3(0, 0, 1)
        if abs(axis.dot(up_ref)) > 0.95:
            up_ref = _V3(1, 0, 0)
        rx = axis.cross(up_ref).norm()
        ry = axis.cross(rx).norm()

        # 8 边形近似底圆
        pts = []
        for i in range(8):
            ang = i * math.pi / 4.0
            off = rx * (math.cos(ang) * base_r) + ry * (math.sin(ang) * base_r)
            wp = base_center + off
            sx, sy, _ = self.camera.project(wp, W, H)
            pts.append(QPointF(sx, sy))

        # 锥侧面
        tip_sx, tip_sy, _ = self.camera.project(tip, W, H)
        tip_pt = QPointF(tip_sx, tip_sy)
        # 每两个相邻底点 + 锥尖构成一个三角形
        body_col = QColor(col); body_col.setAlpha(150)
        p.setPen(QPen(col, 1.2)); p.setBrush(QBrush(body_col))
        for i in range(8):
            a = pts[i]
            b = pts[(i + 1) % 8]
            poly = QPolygonF([a, b, tip_pt])
            p.drawPolygon(poly)
        # 底圆
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(col, 1.2))
        p.drawPolygon(QPolygonF(pts))

        # 底部中心点（世界坐标 pos）明显一点
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(col))
        r = 3.6
        p.drawEllipse(QPointF(px, py), r, r)

        # 名字
        p.setPen(QColor(230, 230, 230))
        f = p.font(); f.setPointSize(8); p.setFont(f)
        p.drawText(QPointF(px + 8, py - 6), obj.name)

    def _draw_lock_line(self, p, W, H):
        """从主机体到锁定目标画一条红色虚线 + 目标处准星"""
        tgt = self.lock_target
        if tgt is None or not getattr(tgt, 'visible', True):
            return
        player = None
        for o in self.objects:
            if getattr(o, 'is_player', False):
                player = o
                break
        if player is None:
            return
        try:
            p_pos, _, _ = player.sample_at(self.current_time)
            t_pos, _, _ = tgt.sample_at(self.current_time)
        except Exception:
            return
        sx1, sy1, _ = self.camera.project(p_pos, W, H)
        sx2, sy2, _ = self.camera.project(t_pos, W, H)
        if not (math.isfinite(sx1) and math.isfinite(sy1) and
                math.isfinite(sx2) and math.isfinite(sy2)):
            return
        pen = QPen(QColor(255, 60, 60, 210), 2, Qt.DashLine)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(sx1, sy1), QPointF(sx2, sy2))
        r = 20
        p.setPen(QPen(QColor(255, 80, 80, 240), 2))
        p.drawEllipse(QPointF(sx2, sy2), r * 0.55, r * 0.55)
        p.drawLine(QPointF(sx2 - r, sy2), QPointF(sx2 - r * 0.35, sy2))
        p.drawLine(QPointF(sx2 + r * 0.35, sy2), QPointF(sx2 + r, sy2))
        p.drawLine(QPointF(sx2, sy2 - r), QPointF(sx2, sy2 - r * 0.35))
        p.drawLine(QPointF(sx2, sy2 + r * 0.35), QPointF(sx2, sy2 + r))


    def _draw_player(self, p, obj, pos, hd, el, px, py, W, H):
        """主机体：三角棱柱 / 箭头，能区分俯仰/滚转/朝向"""
        hovered_body = (obj is self._hover_body_obj)
        hovered_ground = (obj is self._hover_ground_obj) or \
                         (obj is self._drag_obj and self._mode == 'drag_ground')
        hovered = hovered_body or hovered_ground
        # ★ 垂线：从坐标点向下延伸到地面
        if pos.z > 1e-3:
            _pc = QColor(obj.color)
            if hovered:
                _pc = _pc.lighter(160)
            ground = _V3(pos.x, pos.y, 0.0)
            a = self.camera.project(pos, W, H)
            b = self.camera.project(ground, W, H)
            pen = QPen(QColor(_pc.red(), _pc.green(), _pc.blue(), 130), 1.0)
            pen.setStyle(Qt.DashLine)
            pen.setCosmetic(True)
            p.setPen(pen); p.setBrush(Qt.NoBrush)
            p.drawLine(QPointF(a[0], a[1]), QPointF(b[0], b[1]))
            p.setPen(Qt.NoPen)
            if hovered:
                dot_col = QColor(255, 255, 255, 240)
                r = 4.5
            else:
                dot_col = QColor(_pc.red(), _pc.green(), _pc.blue(), 200)
                r = 3.0
            p.setBrush(QBrush(dot_col))
            p.drawEllipse(QPointF(b[0], b[1]), r, r)

        depth = (pos - self.camera.eye()).length()
        scale = max(0.6, min(3.0, depth / 400.0))
        L = 22.0 * scale   # 机头到机尾长度
        Wd = 10.0 * scale  # 半宽
        Ht = 6.0 * scale   # 高度

        # ★ 用完整旋转矩阵求本地三轴（避免俯仰接近 ±90° 时的万向节锁跳变）
        right, fwd, up = _body_frame(hd, el, getattr(obj, 'roll', 0.0))

        # 4 个关键点：机头、机尾上、机尾左下、机尾右下
        nose = pos + fwd * L
        tail_up = pos - fwd * L * 0.6 + up * Ht
        tail_l = pos - fwd * L * 0.6 - up * Ht * 0.4 + right * (-Wd)
        tail_r = pos - fwd * L * 0.6 - up * Ht * 0.4 + right * (Wd)

        def pr(v):
            sx, sy, _ = self.camera.project(v, W, H)
            return QPointF(sx, sy)

        nose_p = pr(nose); tu = pr(tail_up); tl = pr(tail_l); tr = pr(tail_r)
        col = QColor(obj.color)
        if hovered:
            col = col.lighter(160)
        # 两个侧面：机头-尾上-尾左下 / 机头-尾上-尾右下
        back = QColor(col); back.setAlpha(160)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(back))
        p.drawPolygon(QPolygonF([nose_p, tu, tl]))
        p.drawPolygon(QPolygonF([nose_p, tu, tr]))
        # 底面（机头-左下-右下）—— 用亮色区分正反，保持主色不变
        front = QColor(col).lighter(150)
        front.setAlpha(220)
        p.setBrush(QBrush(front))
        p.drawPolygon(QPolygonF([nose_p, tl, tr]))
        # ★ 三边染色：左=红、右=绿、顶脊=白
        p.setBrush(Qt.NoBrush)
        pen_l = QPen(QColor("#e04040"), 2.0)
        pen_l.setCosmetic(True)
        p.setPen(pen_l)
        p.drawLine(nose_p, tl)
        pen_r = QPen(QColor("#40d040"), 2.0)
        pen_r.setCosmetic(True)
        p.setPen(pen_r)
        p.drawLine(nose_p, tr)
        pen_t = QPen(QColor("#f0f0f0"), 2.0)
        pen_t.setCosmetic(True)
        p.setPen(pen_t)
        p.drawLine(nose_p, tu)
        # 尾缘（tl-tu、tr-tu）用主色细线连起来
        pen_tail = QPen(col.lighter(130), 1.0)
        pen_tail.setCosmetic(True)
        p.setPen(pen_tail)
        p.drawLine(tl, tu)
        p.drawLine(tr, tu)
        # 底边（tl-tr）保留主色
        p.drawLine(tl, tr)

        # 中心点（= 世界 pos）
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(col.lighter(140)))
        p.drawEllipse(QPointF(px, py), 4.5, 4.5)
        # 名字
        p.setPen(QColor(240, 240, 240))
        f = p.font(); f.setPointSize(8); p.setFont(f)
        p.drawText(QPointF(px + 10, py - 8), obj.name)


class TargetControlDialog(QDialog):
    """目标控制窗口：3D 场景 + 目标参数 + 主机体参数 + 时间轴"""

    valuesChanged = pyqtSignal()
    closed = pyqtSignal()

    def __init__(self, flight_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_T('target_ctrl_title'))
        self.setWindowFlags(Qt.Window | Qt.WindowSystemMenuHint |
                            Qt.WindowMinMaxButtonsHint |
                            Qt.WindowCloseButtonHint)
        self.setModal(False)
        self.resize(1180, 720)
        # ★ 单独再设一次最大化（某些 Windows 平台上 QDialog 会忽略组合标志）
        try:
            self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        except Exception:
            pass
        # ★ 显式放开尺寸上限，避免默认 MaximumSize 把最大化禁掉
        try:
            self.setMaximumSize(16777215, 16777215)
        except Exception:
            pass

        self._fd = flight_data
        self._updating = False

        # ---- 原点 = (主机体 Lat/Lon, 地面) ----
        # ★ z 原点固定在地面，主机体默认高度 100 米
        self._origin_lat = float(flight_data.get('Latitude', 0.0))
        self._origin_lon = float(flight_data.get('Longitude', 0.0))
        self._origin_alt = 0.0

        # ---- 场景对象 ----
        self._player = _SceneObj(_L(u"主机体", u"Player"), is_player=True)
        self._player.pos = _V3(0.0, 0.0, 100.0)   # ★ 默认高度 100
        self._player.color = QColor("#3090ff")
        self._targets = []          # list[_SceneObj]
        self._player_moves = True

        # ---- 左右栏隐藏状态 ----
        self._left_panel_hidden = False
        self._right_panel_hidden = False
        self._left_panel_width = 260
        self._right_panel_width = 240

        self._current_time = 0.0
        self._duration = 60.0
        self._speed = 1.0
        self._playing = False
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._on_tick)

        # ★ 撤销 / 重做历史
        self._undo_stack = []
        self._redo_stack = []
        self._restoring_undo = False
        self._undo_timer = QTimer(self)
        self._undo_timer.setSingleShot(True)
        self._undo_timer.setInterval(300)
        self._undo_timer.timeout.connect(self._commit_undo)

        self._lock_idx = -1

        self._build_ui()
        self._disable_button_auto_default()
        self._init_default_target()
        self._refresh_target_list()
        self._resimulate_all()
        self._apply_language()

        # ★ 快捷键
        QShortcut(QKeySequence("Ctrl+Z"), self, self._undo)
        QShortcut(QKeySequence("Ctrl+Y"), self, self._redo)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, self._redo)

        # 首次进入后推入初始快照
        QTimer.singleShot(0, self._push_initial_snapshot)

    def _disable_button_auto_default(self):
        """★ 关闭所有按钮的 autoDefault，防止在数值框里回车误触"""
        try:
            for btn in self.findChildren(QPushButton):
                try:
                    btn.setAutoDefault(False)
                    btn.setDefault(False)
                except Exception:
                    pass
        except Exception:
            pass

    # ============================================================
    #                  语言刷新
    # ============================================================
    def _apply_language(self):
        """根据当前 CURRENT_LANG 刷新本窗口里所有文字"""
        try:
            self.setWindowTitle(_T('target_ctrl_title'))
        except Exception:
            pass

        # ---- 顶部时间轴 ----
        try:
            self._lbl_duration.setText(_L(u"时长(秒):", u"Duration(s):"))
            self._lbl_speed.setText(_L(u"速度:", u"Speed:"))
            self.btn_reset_t.setText(u"⏮ " + _L(u"重置", u"Reset"))
            playing = self._playing
            self.btn_play.setText(
                (u"⏸ " + _L(u"暂停", u"Pause")) if playing
                else (u"▶ " + _L(u"播放", u"Play")))
        except Exception:
            pass

        # ---- 目标列表 ----
        try:
            self._lbl_target_list.setText(_L(u"目标列表", u"Targets"))
            self.btn_add_target.setToolTip(_L(u"添加目标", u"Add Target"))
            self.btn_del_target.setToolTip(
                _L(u"删除选中目标", u"Delete Target"))
        except Exception:
            pass

        # ---- 目标参数组 ----
        try:
            self.grp_target.setTitle(_L(u"目标参数", u"Target Params"))
            self._lbl_t_lat.setText(_L(u"纬度 Lat:", u"Lat:"))
            self._lbl_t_lon.setText(_L(u"经度 Lon:", u"Lon:"))
            self._lbl_t_alt.setText(_L(u"高度 Alt:", u"Alt:"))
            self._lbl_t_heading.setText(_L(u"航向:", u"Heading:"))
            self._lbl_t_elev.setText(_L(u"俯仰:", u"Elevation:"))
            self._lbl_t_speed.setText(_L(u"速度:", u"Speed:"))
            self._lbl_t_turn.setText(_L(u"转向率:", u"Turn Rate:"))
            self.chk_t_visible.setText(_L(u"显示", u"Visible"))
            self.btn_reset_target.setText(u"↺ " + _L(u"重置", u"Reset"))
            self.btn_reset_target.setToolTip(_T('reset_target_params'))
        except Exception:
            pass

        # ---- 主机体参数组 ----
        try:
            self.grp_player.setTitle(_L(u"主机体参数", u"Player Params"))
            self._lbl_p_lat.setText(_L(u"纬度 Lat:", u"Lat:"))
            self._lbl_p_lon.setText(_L(u"经度 Lon:", u"Lon:"))
            self._lbl_p_alt.setText(_L(u"高度 Alt:", u"Alt:"))
            self._lbl_p_heading.setText(_L(u"航向:", u"Heading:"))
            self._lbl_p_elev.setText(_L(u"俯仰:", u"Elevation:"))
            self._lbl_p_roll.setText(_L(u"滚转:", u"Roll:"))
            self._lbl_p_speed.setText(_L(u"速度:", u"Speed:"))
            self._lbl_p_turn.setText(_L(u"转向率:", u"Turn Rate:"))
            self.btn_reset_player.setText(u"↺ " + _L(u"重置", u"Reset"))
            self.btn_reset_player.setToolTip(_T('reset_player_params'))
        except Exception:
            pass

        # ---- 底部左右栏 toggle ----
        try:
            self.btn_toggle_left.setText(_L(u"◧ 左栏", u"◧ Left"))
            self.btn_toggle_left.setToolTip(
                _L(u"显示/隐藏左侧栏", u"Show/hide left panel"))
            self.btn_toggle_right.setText(_L(u"右栏 ◨", u"Right ◨"))
            self.btn_toggle_right.setToolTip(
                _L(u"显示/隐藏右侧栏", u"Show/hide right panel"))
        except Exception:
            pass

        # ---- 底部 5 个按钮 ----
        try:
            self.btn_fire_weapons.setText(_L(u"发射武器", u"Fire Weapons"))
            self.btn_fire_guns.setText(_L(u"机炮", u"Fire Guns"))
            self.btn_countermeasures.setText(
                _L(u"干扰弹", u"Countermeasures"))
            self.btn_lock.setText(_L(u"锁定", u"Lock"))
            self.btn_switch_target.setText(
                _L(u"切换目标", u"Switch Target"))
        except Exception:
            pass

        # ---- 刷新画布（底部提示 / 旋转 gizmo 提示文字由 _L 实时求值）----
        try:
            self.canvas.update()
        except Exception:
            pass

    # ============================================================
    #                  底部快捷按钮栏
    # ============================================================
    def _set_hold(self, key, pressed):
        """按住型按钮：按下 1，松开 -1"""
        try:
            self._fd[key] = 1.0 if pressed else -1.0
        except Exception:
            pass
        self.valuesChanged.emit()

    def _find_next_visible_target(self, start_idx):
        """从 start_idx+1 开始循环找第一个可见目标；找不到返回 -1"""
        n = len(self._targets)
        if n == 0:
            return -1
        for k in range(1, n + 1):
            i = (start_idx + k) % n
            if getattr(self._targets[i], 'visible', True):
                return i
        return -1

    def _on_lock_toggled(self, checked):
        """锁定按钮开关：
        · 开 → 找第一个可见目标并锁定；若无可见目标则取消勾选
        · 关 → 清除连线；TargetSelected=0
        """
        try:
            if checked:
                idx = self._find_next_visible_target(-1)
                if idx >= 0:
                    self._lock_idx = idx
                    self.canvas.lock_target = self._targets[idx]
                else:
                    self._lock_idx = -1
                    self.canvas.lock_target = None
                    self.btn_lock.blockSignals(True)
                    self.btn_lock.setChecked(False)
                    self.btn_lock.blockSignals(False)
            else:
                self.canvas.lock_target = None
            # 切换目标按钮使能
            has_lock = (self.canvas.lock_target is not None)
            self.btn_switch_target.setEnabled(
                bool(self.btn_lock.isChecked()) and has_lock)
            # 更新 Target* 到 _fd
            self._sync_to_flight_data()
            self.canvas.update()
            self.valuesChanged.emit()
        except Exception:
            import traceback
            traceback.print_exc()

    def _on_switch_target_clicked(self):
        """切换目标：仅在锁定时有效，自动跳过不可见目标"""
        try:
            if not self.btn_lock.isChecked():
                return
            if not self._targets:
                return
            idx = self._find_next_visible_target(self._lock_idx)
            if idx < 0:
                return
            self._lock_idx = idx
            self.canvas.lock_target = self._targets[idx]
            self._sync_to_flight_data()
            self.canvas.update()
            self.valuesChanged.emit()
        except Exception:
            import traceback
            traceback.print_exc()

    def _sync_lock_target(self):
        """目标列表变化后同步 lock_target 引用（跳过不可见）"""
        try:
            if not self.btn_lock.isChecked():
                self.canvas.lock_target = None
            else:
                cur = self._lock_idx
                invalid = (cur < 0
                           or cur >= len(self._targets)
                           or not getattr(self._targets[cur],
                                          'visible', True))
                if invalid:
                    idx = self._find_next_visible_target(-1)
                    self._lock_idx = idx
                    if idx >= 0:
                        self.canvas.lock_target = self._targets[idx]
                    else:
                        self.canvas.lock_target = None
                        self.btn_lock.blockSignals(True)
                        self.btn_lock.setChecked(False)
                        self.btn_lock.blockSignals(False)
                else:
                    self.canvas.lock_target = self._targets[cur]
            has_lock = (self.canvas.lock_target is not None)
            self.btn_switch_target.setEnabled(
                bool(self.btn_lock.isChecked()) and has_lock)
            self.canvas.update()
            self._sync_to_flight_data()
        except Exception:
            pass

    def _sync_buttons_from_fd(self):
        """从 _fd 反读按钮状态（供外部刷新时调用）"""
        try:
            wv = float(self._fd.get('FireWeapons', -1.0))
            gv = float(self._fd.get('FireGuns', -1.0))
            cv = float(self._fd.get('LaunchCountermeasures', -1.0))
            self.btn_fire_weapons.setDown(wv >= 0.5)
            self.btn_fire_guns.setDown(gv >= 0.5)
            self.btn_countermeasures.setDown(cv >= 0.5)
        except Exception:
            pass

    # ============================================================
    #                  左右栏显隐
    # ============================================================
    def _hide_left_via_action(self):
        try:
            self.btn_toggle_left.setChecked(False)
        except Exception:
            self._hide_left_panel()

    def _hide_right_via_action(self):
        try:
            self.btn_toggle_right.setChecked(False)
        except Exception:
            self._hide_right_panel()

    def _on_show_left_toggled(self, on):
        if getattr(self, '_panel_busy', False):
            return
        self._panel_busy = True
        try:
            if on and self._left_panel_hidden:
                self._show_left_panel()
            elif (not on) and (not self._left_panel_hidden):
                self._hide_left_panel()
        finally:
            self._panel_busy = False

    def _on_show_right_toggled(self, on):
        if getattr(self, '_panel_busy', False):
            return
        self._panel_busy = True
        try:
            if on and self._right_panel_hidden:
                self._show_right_panel()
            elif (not on) and (not self._right_panel_hidden):
                self._hide_right_panel()
        finally:
            self._panel_busy = False

    def _hide_left_panel(self):
        try:
            sizes = self._mid_split.sizes()
            if len(sizes) >= 3 and sizes[0] > 60:
                self._left_panel_width = sizes[0]
            self._left_panel.setVisible(False)
            self._left_panel_hidden = True
            QTimer.singleShot(0, self._relayout_left_hidden)
        except Exception:
            pass

    def _relayout_left_hidden(self):
        try:
            sizes = self._mid_split.sizes()
            if len(sizes) >= 3:
                self._mid_split.setSizes([0, sizes[1] + sizes[0], sizes[2]])
            if not self.isMaximized():
                new_w = self.width() - self._left_panel_width
                if new_w >= 500:
                    self.resize(new_w, self.height())
        except Exception:
            pass

    def _show_left_panel(self):
        try:
            self._left_panel.setVisible(True)
            self._left_panel_hidden = False
            QTimer.singleShot(0, self._relayout_left_shown)
        except Exception:
            pass

    def _relayout_left_shown(self):
        try:
            w = max(200, self._left_panel_width)
            sizes = self._mid_split.sizes()
            if len(sizes) >= 3:
                total = sizes[1]
                self._mid_split.setSizes([w, max(200, total - w), sizes[2]])
            if not self.isMaximized():
                self.resize(self.width() + w, self.height())
        except Exception:
            pass

    def _hide_right_panel(self):
        try:
            sizes = self._mid_split.sizes()
            if len(sizes) >= 3 and sizes[2] > 60:
                self._right_panel_width = sizes[2]
            self._right_panel.setVisible(False)
            self._right_panel_hidden = True
            QTimer.singleShot(0, self._relayout_right_hidden)
        except Exception:
            pass

    def _relayout_right_hidden(self):
        try:
            sizes = self._mid_split.sizes()
            if len(sizes) >= 3:
                self._mid_split.setSizes([sizes[0], sizes[1] + sizes[2], 0])
            if not self.isMaximized():
                new_w = self.width() - self._right_panel_width
                if new_w >= 500:
                    self.resize(new_w, self.height())
        except Exception:
            pass

    def _show_right_panel(self):
        try:
            self._right_panel.setVisible(True)
            self._right_panel_hidden = False
            QTimer.singleShot(0, self._relayout_right_shown)
        except Exception:
            pass

    def _relayout_right_shown(self):
        try:
            w = max(200, self._right_panel_width)
            sizes = self._mid_split.sizes()
            if len(sizes) >= 3:
                total = sizes[1]
                self._mid_split.setSizes([sizes[0], max(200, total - w), w])
            if not self.isMaximized():
                self.resize(self.width() + w, self.height())
        except Exception:
            pass

    # ============================================================
    #                       UI 构建
    # ============================================================

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ---------- 顶部时间轴 ----------
        top = QHBoxLayout()
        top.setSpacing(6)

        self._lbl_duration = QLabel(_L(u"时长(秒):", u"Duration(s):"))
        top.addWidget(self._lbl_duration)
        self.spin_duration = QDoubleSpinBox()
        self.spin_duration.setRange(0.5, 3600.0)
        self.spin_duration.setDecimals(1)
        self.spin_duration.setSingleStep(10.0)
        self.spin_duration.setValue(self._duration)
        self.spin_duration.setFixedWidth(80)
        self.spin_duration.valueChanged.connect(self._on_duration_changed)
        top.addWidget(self.spin_duration)

        self.slider_time = QSlider(Qt.Horizontal)
        self.slider_time.setRange(0, 10000)
        self.slider_time.setValue(0)
        self.slider_time.sliderMoved.connect(self._on_slider_moved)
        top.addWidget(self.slider_time, 1)

        self.lbl_time = QLabel(u"0.0 / 60.0 s")
        self.lbl_time.setFixedWidth(120)
        self.lbl_time.setAlignment(Qt.AlignCenter)
        self.lbl_time.setStyleSheet(
            "background:#2a2d31; color:#e0e0e0; border:1px solid #444;"
            "border-radius:3px; padding:1px 4px;")
        top.addWidget(self.lbl_time)

        self.btn_play = QPushButton(u"▶ " + _L(u"播放", u"Play"))
        self.btn_play.setFixedWidth(70)
        self.btn_play.clicked.connect(self._on_play_pause)
        top.addWidget(self.btn_play)

        self.btn_reset_t = QPushButton(u"⏮ " + _L(u"重置", u"Reset"))
        self.btn_reset_t.setFixedWidth(70)
        self.btn_reset_t.clicked.connect(self._on_reset_time)
        top.addWidget(self.btn_reset_t)

        self._lbl_speed = QLabel(_L(u"速度:", u"Speed:"))
        top.addWidget(self._lbl_speed)
        self.cmb_speed = QComboBox()
        for s in ('0.25', '0.5', '1.0', '2.0', '4.0', '8.0'):
            self.cmb_speed.addItem(s + u"x", float(s))
        self.cmb_speed.setCurrentIndex(2)
        self.cmb_speed.setFixedWidth(70)
        self.cmb_speed.currentIndexChanged.connect(self._on_speed_changed)
        top.addWidget(self.cmb_speed)

        root.addLayout(top)

        # ---------- 中部三分区 ----------
        mid = QSplitter(Qt.Horizontal)
        mid.setChildrenCollapsible(False)
        mid.setHandleWidth(3)
        mid.setStyleSheet(
            "QSplitter::handle { background-color: #4a4a4a; }"
            "QSplitter::handle:hover { background-color: #00a0ff; }")
        self._mid_split = mid

        # 左：目标列表 + 参数
        left = QWidget()
        left.setMinimumWidth(180)
        left.setMaximumWidth(460)
        self._left_panel = left
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(4)

        hdr = QHBoxLayout()
        self._lbl_target_list = QLabel(_L(u"目标列表", u"Targets"))
        hdr.addWidget(self._lbl_target_list)
        hdr.addStretch(1)
        self.btn_add_target = QPushButton(u"＋")
        self.btn_add_target.setFixedWidth(28)
        self.btn_add_target.setToolTip(_L(u"添加目标", u"Add Target"))
        self.btn_add_target.clicked.connect(self._add_target)
        hdr.addWidget(self.btn_add_target)
        self.btn_del_target = QPushButton(u"🗑")
        self.btn_del_target.setFixedWidth(28)
        self.btn_del_target.setToolTip(_L(u"删除选中目标", u"Delete Target"))
        self.btn_del_target.clicked.connect(self._del_target)
        hdr.addWidget(self.btn_del_target)
        ll.addLayout(hdr)

        self.lst_targets = QListWidget()
        self.lst_targets.currentRowChanged.connect(self._on_target_selected)
        ll.addWidget(self.lst_targets, 1)

        self.grp_target = QGroupBox(_L(u"目标参数", u"Target Params"))
        _t_outer = QVBoxLayout(self.grp_target)
        _t_outer.setContentsMargins(6, 6, 6, 6)
        _t_outer.setSpacing(4)
        tf = QFormLayout()
        tf.setSpacing(4)
        tf.setLabelAlignment(Qt.AlignRight)
        _t_outer.addLayout(tf)

        self.spin_t_lat = QDoubleSpinBox()
        self.spin_t_lat.setRange(-1e8, 1e8); self.spin_t_lat.setDecimals(2)
        self.spin_t_lat.setKeyboardTracking(False)
        self.spin_t_lon = QDoubleSpinBox()
        self.spin_t_lon.setRange(-1e8, 1e8); self.spin_t_lon.setDecimals(2)
        self.spin_t_lon.setKeyboardTracking(False)
        self.spin_t_alt = QDoubleSpinBox()
        self.spin_t_alt.setRange(-10000.0, 100000.0); self.spin_t_alt.setDecimals(2)
        self.spin_t_alt.setKeyboardTracking(False)

        self.spin_t_heading = QDoubleSpinBox()
        self.spin_t_heading.setRange(-36000.0, 36000.0)
        self.spin_t_heading.setDecimals(2)
        self.spin_t_heading.setSuffix(u" °")
        self.spin_t_heading.setKeyboardTracking(False)

        self.spin_t_elev = QDoubleSpinBox()
        self.spin_t_elev.setRange(-36000.0, 36000.0)
        self.spin_t_elev.setDecimals(2)
        self.spin_t_elev.setSuffix(u" °")
        self.spin_t_elev.setKeyboardTracking(False)

        self.spin_t_speed = QDoubleSpinBox()
        self.spin_t_speed.setRange(-1000.0, 1000.0); self.spin_t_speed.setDecimals(2)
        self.spin_t_speed.setSuffix(u" m/s")
        self.spin_t_speed.setKeyboardTracking(False)

        self.spin_t_turn = QDoubleSpinBox()
        self.spin_t_turn.setRange(-360.0, 360.0); self.spin_t_turn.setDecimals(2)
        self.spin_t_turn.setSuffix(u" °/s")
        self.spin_t_turn.setKeyboardTracking(False)

        self._lbl_t_lat = QLabel(_L(u"纬度 Lat:", u"Lat:"))
        self._lbl_t_lon = QLabel(_L(u"经度 Lon:", u"Lon:"))
        self._lbl_t_alt = QLabel(_L(u"高度 Alt:", u"Alt:"))
        self._lbl_t_heading = QLabel(_L(u"航向:", u"Heading:"))
        self._lbl_t_elev = QLabel(_L(u"俯仰:", u"Elevation:"))
        self._lbl_t_speed = QLabel(_L(u"速度:", u"Speed:"))
        self._lbl_t_turn = QLabel(_L(u"转向率:", u"Turn Rate:"))
        tf.addRow(self._lbl_t_lat, self.spin_t_lat)
        tf.addRow(self._lbl_t_lon, self.spin_t_lon)
        tf.addRow(self._lbl_t_alt, self.spin_t_alt)
        tf.addRow(self._lbl_t_heading, self.spin_t_heading)
        tf.addRow(self._lbl_t_elev, self.spin_t_elev)
        tf.addRow(self._lbl_t_speed, self.spin_t_speed)
        tf.addRow(self._lbl_t_turn, self.spin_t_turn)

        self.chk_t_visible = QCheckBox(_L(u"显示", u"Visible"))
        self.chk_t_visible.setChecked(True)
        _last_row_t = QWidget()
        _lr_t = QHBoxLayout(_last_row_t)
        _lr_t.setContentsMargins(0, 0, 0, 0)
        _lr_t.setSpacing(4)
        _lr_t.addWidget(self.chk_t_visible)
        _lr_t.addStretch(1)
        self.btn_reset_target = QPushButton(u"↺ " + _L(u"重置", u"Reset"))
        self.btn_reset_target.setFixedHeight(22)
        self.btn_reset_target.setToolTip(_T('reset_target_params'))
        self.btn_reset_target.clicked.connect(self._on_reset_target)
        _lr_t.addWidget(self.btn_reset_target)
        tf.addRow(u"", _last_row_t)

        ll.addWidget(self.grp_target)
        ll.addStretch(1)
        mid.addWidget(left)

        # 中：3D 画布 + 下方快捷按钮栏
        canvas_wrap = QWidget()
        cw_lay = QVBoxLayout(canvas_wrap)
        cw_lay.setContentsMargins(0, 0, 0, 0)
        cw_lay.setSpacing(4)

        self.canvas = Track3DCanvas(self)
        self.canvas.objectsChanged.connect(self._on_canvas_objects_changed)
        self.canvas.objectPicked.connect(self._on_canvas_object_picked)
        cw_lay.addWidget(self.canvas, 1)

        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(6)
        bar.addStretch(1)

        self.btn_fire_weapons = QPushButton(
            _L(u"发射武器", u"Fire Weapons"))
        self.btn_fire_weapons.setFixedHeight(28)
        self.btn_fire_weapons.setMinimumWidth(120)
        self.btn_fire_weapons.setFocusPolicy(Qt.NoFocus)
        self.btn_fire_weapons.setStyleSheet(
            "QPushButton{background:#3a1f1f;color:#ffd0d0;"
            "border:1px solid #804040;border-radius:3px;font-weight:bold;}"
            "QPushButton:hover{background:#4a2828;}"
            "QPushButton:pressed{background:#d03030;color:#ffffff;"
            "border-color:#ff6060;}")
        bar.addWidget(self.btn_fire_weapons)

        self.btn_fire_guns = QPushButton(
            _L(u"机炮", u"Fire Guns"))
        self.btn_fire_guns.setFixedHeight(28)
        self.btn_fire_guns.setMinimumWidth(120)
        self.btn_fire_guns.setFocusPolicy(Qt.NoFocus)
        self.btn_fire_guns.setStyleSheet(
            "QPushButton{background:#3a2c1a;color:#ffe0b0;"
            "border:1px solid #805a30;border-radius:3px;font-weight:bold;}"
            "QPushButton:hover{background:#4a3822;}"
            "QPushButton:pressed{background:#d08020;color:#ffffff;"
            "border-color:#ffb060;}")
        bar.addWidget(self.btn_fire_guns)

        self.btn_countermeasures = QPushButton(
            _L(u"干扰弹", u"Countermeasures"))
        self.btn_countermeasures.setFixedHeight(28)
        self.btn_countermeasures.setMinimumWidth(120)
        self.btn_countermeasures.setFocusPolicy(Qt.NoFocus)
        self.btn_countermeasures.setStyleSheet(
            "QPushButton{background:#3a3418;color:#ffeec0;"
            "border:1px solid #807a30;border-radius:3px;font-weight:bold;}"
            "QPushButton:hover{background:#4a4422;}"
            "QPushButton:pressed{background:#d0c020;color:#000000;"
            "border-color:#ffec60;}")
        bar.addWidget(self.btn_countermeasures)

        self.btn_lock = QPushButton(
            _L(u"锁定", u"Lock"))
        self.btn_lock.setCheckable(True)
        self.btn_lock.setFixedHeight(28)
        self.btn_lock.setMinimumWidth(100)
        self.btn_lock.setFocusPolicy(Qt.NoFocus)
        self.btn_lock.setStyleSheet(
            "QPushButton{background:#1e3a20;color:#c8ffd0;"
            "border:1px solid #408050;border-radius:3px;font-weight:bold;}"
            "QPushButton:hover{background:#284a2c;}"
            "QPushButton:checked{background:#30c050;color:#ffffff;"
            "border-color:#60ff80;}")
        bar.addWidget(self.btn_lock)

        self.btn_switch_target = QPushButton(
            _L(u"切换目标", u"Switch Target"))
        self.btn_switch_target.setFixedHeight(28)
        self.btn_switch_target.setMinimumWidth(100)
        self.btn_switch_target.setFocusPolicy(Qt.NoFocus)
        self.btn_switch_target.setStyleSheet(
            "QPushButton{background:#2a2038;color:#d8c8f0;"
            "border:1px solid #604880;border-radius:3px;font-weight:bold;}"
            "QPushButton:hover{background:#3a2a50;}"
            "QPushButton:pressed{background:#8050d0;color:#ffffff;"
            "border-color:#b090ff;}"
            "QPushButton:disabled{background:#2a2a2a;color:#666;"
            "border-color:#444;}")
        bar.addWidget(self.btn_switch_target)

        bar.addStretch(1)
        cw_lay.addLayout(bar)

        # 信号连接
        self.btn_fire_weapons.pressed.connect(
            lambda: self._set_hold('FireWeapons', True))
        self.btn_fire_weapons.released.connect(
            lambda: self._set_hold('FireWeapons', False))
        self.btn_fire_guns.pressed.connect(
            lambda: self._set_hold('FireGuns', True))
        self.btn_fire_guns.released.connect(
            lambda: self._set_hold('FireGuns', False))
        self.btn_countermeasures.pressed.connect(
            lambda: self._set_hold('LaunchCountermeasures', True))
        self.btn_countermeasures.released.connect(
            lambda: self._set_hold('LaunchCountermeasures', False))
        self.btn_lock.toggled.connect(self._on_lock_toggled)
        self.btn_switch_target.clicked.connect(self._on_switch_target_clicked)

        # 初始时"切换目标"按钮不可用（未锁定）
        self.btn_switch_target.setEnabled(False)

        mid.addWidget(canvas_wrap)

        # 右：主机体参数
        right = QWidget()
        right.setMinimumWidth(180)
        right.setMaximumWidth(460)
        self._right_panel = right
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(4)

        right_hdr = QHBoxLayout()
        right_hdr.addStretch(1)
        rl.addLayout(right_hdr)

        self.grp_player = QGroupBox(_L(u"主机体参数", u"Player Params"))
        _p_outer = QVBoxLayout(self.grp_player)
        _p_outer.setContentsMargins(6, 6, 6, 6)
        _p_outer.setSpacing(4)
        pf = QFormLayout()
        pf.setSpacing(4)
        pf.setLabelAlignment(Qt.AlignRight)
        _p_outer.addLayout(pf)

        self.spin_p_lat = QDoubleSpinBox()
        self.spin_p_lat.setRange(-1e8, 1e8); self.spin_p_lat.setDecimals(2)
        self.spin_p_lat.setKeyboardTracking(False)
        self.spin_p_lon = QDoubleSpinBox()
        self.spin_p_lon.setRange(-1e8, 1e8); self.spin_p_lon.setDecimals(2)
        self.spin_p_lon.setKeyboardTracking(False)
        self.spin_p_alt = QDoubleSpinBox()
        self.spin_p_alt.setRange(-10000.0, 100000.0); self.spin_p_alt.setDecimals(2)
        self.spin_p_alt.setKeyboardTracking(False)

        self.spin_p_heading = QDoubleSpinBox()
        self.spin_p_heading.setRange(-36000.0, 36000.0)
        self.spin_p_heading.setDecimals(2)
        self.spin_p_heading.setSuffix(u" °")
        self.spin_p_heading.setKeyboardTracking(False)

        self.spin_p_elev = QDoubleSpinBox()
        self.spin_p_elev.setRange(-36000.0, 36000.0)
        self.spin_p_elev.setDecimals(2)
        self.spin_p_elev.setSuffix(u" °")
        self.spin_p_elev.setKeyboardTracking(False)

        self.spin_p_roll = QDoubleSpinBox()
        self.spin_p_roll.setRange(-36000.0, 36000.0)
        self.spin_p_roll.setDecimals(2)
        self.spin_p_roll.setSuffix(u" °")
        self.spin_p_roll.setKeyboardTracking(False)

        self.spin_p_speed = QDoubleSpinBox()
        self.spin_p_speed.setRange(-1000.0, 1000.0); self.spin_p_speed.setDecimals(2)
        self.spin_p_speed.setSuffix(u" m/s")
        self.spin_p_speed.setKeyboardTracking(False)

        self.spin_p_turn = QDoubleSpinBox()
        self.spin_p_turn.setRange(-360.0, 360.0); self.spin_p_turn.setDecimals(2)
        self.spin_p_turn.setSuffix(u" °/s")
        self.spin_p_turn.setKeyboardTracking(False)

        self._lbl_p_lat = QLabel(_L(u"纬度 Lat:", u"Lat:"))
        self._lbl_p_lon = QLabel(_L(u"经度 Lon:", u"Lon:"))
        self._lbl_p_alt = QLabel(_L(u"高度 Alt:", u"Alt:"))
        self._lbl_p_heading = QLabel(_L(u"航向:", u"Heading:"))
        self._lbl_p_elev = QLabel(_L(u"俯仰:", u"Elevation:"))
        self._lbl_p_roll = QLabel(_L(u"滚转:", u"Roll:"))
        self._lbl_p_speed = QLabel(_L(u"速度:", u"Speed:"))
        self._lbl_p_turn = QLabel(_L(u"转向率:", u"Turn Rate:"))
        pf.addRow(self._lbl_p_lat, self.spin_p_lat)
        pf.addRow(self._lbl_p_lon, self.spin_p_lon)
        pf.addRow(self._lbl_p_alt, self.spin_p_alt)
        pf.addRow(self._lbl_p_heading, self.spin_p_heading)
        pf.addRow(self._lbl_p_elev, self.spin_p_elev)
        pf.addRow(self._lbl_p_roll, self.spin_p_roll)
        pf.addRow(self._lbl_p_speed, self.spin_p_speed)
        pf.addRow(self._lbl_p_turn, self.spin_p_turn)

        _last_row_p = QWidget()
        _lr_p = QHBoxLayout(_last_row_p)
        _lr_p.setContentsMargins(0, 0, 0, 0)
        _lr_p.setSpacing(4)
        _lr_p.addStretch(1)
        self.btn_reset_player = QPushButton(u"↺ " + _L(u"重置", u"Reset"))
        self.btn_reset_player.setFixedHeight(22)
        self.btn_reset_player.setToolTip(_T('reset_player_params'))
        self.btn_reset_player.clicked.connect(self._on_reset_player)
        _lr_p.addWidget(self.btn_reset_player)
        pf.addRow(u"", _last_row_p)

        rl.addWidget(self.grp_player)
        rl.addStretch(1)
        mid.addWidget(right)
        mid.setStretchFactor(0, 0)
        mid.setStretchFactor(1, 1)
        mid.setStretchFactor(2, 0)
        mid.setSizes([260, 660, 240])

        root.addWidget(mid, 1)

        # 底部：左右栏显隐 + 关闭
        bottom = QHBoxLayout()
        bottom.addStretch(1)

        # ★ 左右栏显隐按钮
        self.btn_toggle_left = QPushButton(_L(u"◧ 左栏", u"◧ Left"))
        self.btn_toggle_left.setCheckable(True)
        self.btn_toggle_left.setChecked(True)
        self.btn_toggle_left.setFixedHeight(24)
        self.btn_toggle_left.setToolTip(_L(u"显示/隐藏左侧栏", u"Show/hide left panel"))
        self.btn_toggle_left.toggled.connect(self._on_show_left_toggled)
        bottom.addWidget(self.btn_toggle_left)

        self.btn_toggle_right = QPushButton(_L(u"右栏 ◨", u"Right ◨"))
        self.btn_toggle_right.setCheckable(True)
        self.btn_toggle_right.setChecked(True)
        self.btn_toggle_right.setFixedHeight(24)
        self.btn_toggle_right.setToolTip(_L(u"显示/隐藏右侧栏", u"Show/hide right panel"))
        self.btn_toggle_right.toggled.connect(self._on_show_right_toggled)
        bottom.addWidget(self.btn_toggle_right)

        root.addLayout(bottom)

        # ---- 信号连接 ----
        for sp in (self.spin_t_lat, self.spin_t_lon, self.spin_t_alt,
                   self.spin_t_heading, self.spin_t_elev,
                   self.spin_t_speed, self.spin_t_turn):
            sp.valueChanged.connect(self._on_target_param_changed)
        self.chk_t_visible.toggled.connect(self._on_target_param_changed)

        for sp in (self.spin_p_lat, self.spin_p_lon, self.spin_p_alt,
                   self.spin_p_heading, self.spin_p_elev, self.spin_p_roll,
                   self.spin_p_speed, self.spin_p_turn):
            sp.valueChanged.connect(self._on_player_param_changed)

        # 初始化主机体参数显示
        self._updating = True
        self.spin_p_lat.setValue(self._origin_lat)
        self.spin_p_lon.setValue(self._origin_lon)
        self.spin_p_alt.setValue(self._origin_alt)
        self._updating = False

    # ============================================================
    #                       默认目标
    # ============================================================

    def _init_default_target(self):
        """初始目标：固定位置（纬度 +100，高度 100）"""
        t = _SceneObj(_L(u"目标1", u"Target1"), is_player=False)
        t.pos = _V3(0.0, 100.0, 100.0)
        t.heading = 0.0
        t.elevation = 0.0
        t.speed = 0.0
        t.turn_rate = 0.0
        self._targets.append(t)

    # ============================================================
    #                  撤销 / 重做
    # ============================================================
    def _push_initial_snapshot(self):
        if not self._undo_stack:
            self._undo_stack.append(self.get_scene_state())

    def _trigger_undo(self):
        if self._restoring_undo:
            return
        self._undo_timer.start()

    def _commit_undo(self):
        if self._restoring_undo:
            return
        snap = self.get_scene_state()
        if self._undo_stack and self._undo_stack[-1] == snap:
            return
        self._undo_stack.append(snap)
        if len(self._undo_stack) > 100:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def _undo(self):
        if self._restoring_undo:
            return
        # 把当前状态也提交（防止还没 commit 的改动丢失）
        self._undo_timer.stop()
        cur = self.get_scene_state()
        if not self._undo_stack:
            self._undo_stack.append(cur)
            return
        if self._undo_stack[-1] != cur:
            self._undo_stack.append(cur)
        if len(self._undo_stack) < 2:
            return
        self._redo_stack.append(self._undo_stack.pop())
        self._restoring_undo = True
        try:
            self.load_scene_state(self._undo_stack[-1])
        finally:
            self._restoring_undo = False

    def _redo(self):
        if self._restoring_undo:
            return
        if not self._redo_stack:
            return
        snap = self._redo_stack.pop()
        self._undo_stack.append(snap)
        self._restoring_undo = True
        try:
            self.load_scene_state(snap)
        finally:
            self._restoring_undo = False

    # ============================================================
    #                       时间轴
    # ============================================================

    def _on_duration_changed(self, v):
        self._duration = float(v)
        self._resimulate_all()
        self._refresh_time_label()

    def _on_slider_moved(self, value):
        self._current_time = (value / 10000.0) * self._duration
        self.canvas.set_time(self._current_time)
        self._refresh_time_label()
        self._sync_live_positions()
        self._sync_to_flight_data()
        self.valuesChanged.emit()

    def _on_speed_changed(self, idx):
        try:
            self._speed = float(self.cmb_speed.currentData())
        except Exception:
            self._speed = 1.0

    def _on_play_pause(self):
        self._playing = not self._playing
        if self._playing:
            if self._current_time >= self._duration - 1e-6:
                self._current_time = 0.0
            self._timer.start()
            self.btn_play.setText(u"⏸ " + _L(u"暂停", u"Pause"))
        else:
            self._timer.stop()
            self.btn_play.setText(u"▶ " + _L(u"播放", u"Play"))

    def _on_reset_time(self):
        self._playing = False
        self._timer.stop()
        self.btn_play.setText(u"▶ " + _L(u"播放", u"Play"))
        self._current_time = 0.0
        self.canvas.set_time(0.0)
        self._refresh_time_label()
        self._sync_live_positions()
        self._sync_to_flight_data()
        self.valuesChanged.emit()

    def _on_tick(self):
        if not self._playing:
            return
        self._current_time += 0.03 * self._speed
        if self._current_time >= self._duration:
            self._current_time = self._duration
            self._playing = False
            self._timer.stop()
            self.btn_play.setText(u"▶ " + _L(u"播放", u"Play"))
        self.canvas.set_time(self._current_time)
        self._refresh_time_label()
        self._sync_live_positions()
        self._sync_to_flight_data()
        self.valuesChanged.emit()

    def _refresh_time_label(self):
        self.lbl_time.setText(u"%.1f / %.1f s" %
                              (self._current_time, self._duration))
        # 同步进度条
        if self._duration > 1e-6:
            v = int(self._current_time / self._duration * 10000)
            self.slider_time.blockSignals(True)
            self.slider_time.setValue(v)
            self.slider_time.blockSignals(False)

    # ============================================================
    #                       目标列表
    # ============================================================

    def _refresh_target_list(self):
        self._updating = True
        self.lst_targets.clear()
        for t in self._targets:
            visible = getattr(t, 'visible', True)
            prefix = u"" if visible else u"🚫 "
            it = QListWidgetItem(prefix + t.name)
            if visible:
                it.setForeground(t.color)
            else:
                gray = QColor(t.color)
                gray.setAlpha(120)
                it.setForeground(gray)
            self.lst_targets.addItem(it)
        if self._targets:
            self.lst_targets.setCurrentRow(0)
        self._updating = False
        self._load_selected_target_params()
        try:
            self._sync_lock_target()
        except Exception:
            pass

    def _add_target(self):
        n = len(self._targets) + 1
        t = _SceneObj(_L(u"目标%d", u"Target%d") % n, is_player=False)
        t.pos = _V3(0.0, 100.0, 100.0)
        t.heading = 0.0
        t.elevation = 0.0
        self._targets.append(t)
        self._refresh_target_list()
        self._resimulate_all()

    def _del_target(self):
        idx = self.lst_targets.currentRow()
        if 0 <= idx < len(self._targets):
            del self._targets[idx]
            self._refresh_target_list()
            self._resimulate_all()

    def _on_target_selected(self, idx):
        if self._updating:
            return
        self._load_selected_target_params()

    def _load_selected_target_params(self):
        idx = self.lst_targets.currentRow()
        self._updating = True
        try:
            if 0 <= idx < len(self._targets):
                t = self._targets[idx]
                # 相对原点 → Lat/Lon/Alt
                lat = self._origin_lat + t.pos.y
                lon = self._origin_lon + t.pos.x
                alt = self._origin_alt + t.pos.z
                self.spin_t_lat.setValue(lat)
                self.spin_t_lon.setValue(lon)
                self.spin_t_alt.setValue(alt)
                self.spin_t_heading.setValue(t.heading)
                self.spin_t_elev.setValue(t.elevation)
                self.spin_t_speed.setValue(t.speed)
                self.spin_t_turn.setValue(t.turn_rate)
                self.chk_t_visible.setChecked(t.visible)
                self.grp_target.setEnabled(True)
            else:
                self.grp_target.setEnabled(False)
        finally:
            self._updating = False

    def _on_target_param_changed(self, *args):
        if self._updating:
            return
        idx = self.lst_targets.currentRow()
        if not (0 <= idx < len(self._targets)):
            return
        t = self._targets[idx]
        sender = self.sender()

        # 只是切换可见性 → 不动时间/位置
        if sender is self.chk_t_visible:
            t.visible = self.chk_t_visible.isChecked()
            self._update_list_item_color(idx)
            self._sync_lock_target()
            self._sync_to_flight_data()
            self.valuesChanged.emit()
            return

        # ★ 只更新"用户真正在改的那个字段"作为起点
        if sender in (self.spin_t_lat, self.spin_t_lon, self.spin_t_alt):
            t.pos = _V3(self.spin_t_lon.value() - self._origin_lon,
                        self.spin_t_lat.value() - self._origin_lat,
                        self.spin_t_alt.value() - self._origin_alt)
        if sender is self.spin_t_heading:
            t.heading = float(self.spin_t_heading.value())
        if sender is self.spin_t_elev:
            t.elevation = float(self.spin_t_elev.value())
        if sender is self.spin_t_speed:
            t.speed = float(self.spin_t_speed.value())
        if sender is self.spin_t_turn:
            t.turn_rate = float(self.spin_t_turn.value())
        if sender is self.chk_t_visible:
            t.visible = self.chk_t_visible.isChecked()

        self._update_list_item_color(idx)
        self._resimulate_all()
        self._sync_lock_target()
        self._sync_to_flight_data()
        self.valuesChanged.emit()

    def _update_list_item_color(self, idx):
        if 0 <= idx < self.lst_targets.count():
            item = self.lst_targets.item(idx)
            t = self._targets[idx]
            if item is not None:
                visible = getattr(t, 'visible', True)
                item.setText((u"" if visible else u"🚫 ") + t.name)
                if visible:
                    item.setForeground(t.color)
                else:
                    gray = QColor(t.color)
                    gray.setAlpha(120)
                    item.setForeground(gray)

    # ============================================================
    #                       主机体参数
    # ============================================================

    def _on_player_param_changed(self, *args):
        if self._updating:
            return
        p = self._player
        sender = self.sender()

        # ★ 只更新"用户真正在改的那个字段"作为起点，避免播放时
        #   spinbox 里显示的实时值被误当成起点覆盖掉
        if sender in (self.spin_p_lat, self.spin_p_lon, self.spin_p_alt):
            p.pos = _V3(self.spin_p_lon.value() - self._origin_lon,
                        self.spin_p_lat.value() - self._origin_lat,
                        self.spin_p_alt.value() - self._origin_alt)
        if sender is self.spin_p_heading:
            p.heading = float(self.spin_p_heading.value())
        if sender is self.spin_p_elev:
            p.elevation = float(self.spin_p_elev.value())
        if sender is self.spin_p_roll:
            p.roll = float(self.spin_p_roll.value())
        if sender is self.spin_p_speed:
            p.speed = float(self.spin_p_speed.value())
        if sender is self.spin_p_turn:
            p.turn_rate = float(self.spin_p_turn.value())

        self._resimulate_all()
        self._sync_to_flight_data()
        self.valuesChanged.emit()

    def _on_player_move_toggled(self, checked):
        """已废弃：主机体始终按速度运动"""
        self._player_moves = True
        self._resimulate_all()
        self._sync_to_flight_data()
        self.valuesChanged.emit()

    # ---------------- 重置 ----------------

    def _on_reset_target(self):
        idx = self.lst_targets.currentRow()
        if not (0 <= idx < len(self._targets)):
            return
        t = self._targets[idx]
        t.pos = _V3(0.0, 100.0, 100.0)
        t.heading = 0.0
        t.elevation = 0.0
        t.speed = 0.0
        t.turn_rate = 0.0
        t.visible = True
        self._updating = True
        try:
            self.spin_t_lat.setValue(self._origin_lat + t.pos.y)
            self.spin_t_lon.setValue(self._origin_lon + t.pos.x)
            self.spin_t_alt.setValue(self._origin_alt + t.pos.z)
            self.spin_t_heading.setValue(t.heading)
            self.spin_t_elev.setValue(t.elevation)
            self.spin_t_speed.setValue(0.0)
            self.spin_t_turn.setValue(0.0)
            self.chk_t_visible.setChecked(True)
        finally:
            self._updating = False
        self._resimulate_all()
        self._sync_lock_target()
        self._sync_to_flight_data()
        self.valuesChanged.emit()

    def _on_reset_player(self):
        self._updating = True
        try:
            self._player.pos = _V3(0.0, 0.0, 100.0)
            self._player.heading = 0.0
            self._player.elevation = 0.0
            self._player.roll = 0.0
            self._player.speed = 0.0
            self._player.turn_rate = 0.0
            self.spin_p_lat.setValue(self._origin_lat)
            self.spin_p_lon.setValue(self._origin_lon)
            self.spin_p_alt.setValue(100.0)
            self.spin_p_heading.setValue(0.0)
            self.spin_p_elev.setValue(0.0)
            self.spin_p_roll.setValue(0.0)
            self.spin_p_speed.setValue(0.0)
            self.spin_p_turn.setValue(0.0)
        finally:
            self._updating = False
        self._resimulate_all()
        self._sync_to_flight_data()
        self.valuesChanged.emit()

    # ---------------- 场景状态序列化 ----------------

    def get_scene_state(self):
        return {
            "duration": self._duration,
            "current_time": self._current_time,
            "player": {
                "pos": [self._player.pos.x, self._player.pos.y, self._player.pos.z],
                "heading": self._player.heading,
                "elevation": self._player.elevation,
                "roll": self._player.roll,
                "speed": self._player.speed,
                "turn_rate": self._player.turn_rate,
                "moves": self._player_moves,
            },
            "targets": [
                {
                    "name": t.name,
                    "pos": [t.pos.x, t.pos.y, t.pos.z],
                    "heading": t.heading,
                    "elevation": t.elevation,
                    "speed": t.speed,
                    "turn_rate": t.turn_rate,
                    "visible": t.visible,
                    "color": t.color.name(),
                }
                for t in self._targets
            ],
        }

    def load_scene_state(self, state):
        if not state:
            return
        try:
            self._duration = float(state.get("duration", 60.0))
            self.spin_duration.blockSignals(True)
            self.spin_duration.setValue(self._duration)
            self.spin_duration.blockSignals(False)
            self._current_time = float(state.get("current_time", 0.0))
            # player
            pl = state.get("player", {}) or {}
            pos = pl.get("pos", [0.0, 0.0, 100.0])
            self._player.pos = _V3(*pos)
            self._player.heading = float(pl.get("heading", 0.0))
            self._player.elevation = float(pl.get("elevation", 0.0))
            self._player.roll = float(pl.get("roll", 0.0))
            self._player.speed = float(pl.get("speed", 0.0))
            self._player.turn_rate = float(pl.get("turn_rate", 0.0))
            self._player_moves = True
            # targets
            self._targets = []
            for td in state.get("targets", []) or []:
                t = _SceneObj(td.get("name", u"Target"), is_player=False)
                tpos = td.get("pos", [0.0, 100.0, 100.0])
                t.pos = _V3(*tpos)
                t.heading = float(td.get("heading", 0.0))
                t.elevation = float(td.get("elevation", 0.0))
                t.speed = float(td.get("speed", 0.0))
                t.turn_rate = float(td.get("turn_rate", 0.0))
                t.visible = bool(td.get("visible", True))
                col = td.get("color", None)
                if col:
                    try:
                        t.color = QColor(col)
                    except Exception:
                        pass
                self._targets.append(t)
            # 更新 UI 显示
            self._updating = True
            try:
                self.spin_p_lat.setValue(self._origin_lat + self._player.pos.y)
                self.spin_p_lon.setValue(self._origin_lon + self._player.pos.x)
                self.spin_p_alt.setValue(self._origin_alt + self._player.pos.z)
                self.spin_p_heading.setValue(self._player.heading)
                self.spin_p_elev.setValue(self._player.elevation)
                self.spin_p_roll.setValue(self._player.roll)
                self.spin_p_speed.setValue(self._player.speed)
                self.spin_p_turn.setValue(self._player.turn_rate)
            finally:
                self._updating = False
            self._refresh_target_list()
            self._resimulate_all()
            self._refresh_time_label()
        except Exception:
            pass

    # ============================================================
    #                       模拟 + 同步
    # ============================================================

    def _sync_live_positions(self):
        """把当前时刻的实际位置写回数值框（播放 / 拖时间轴时调用）"""
        try:
            self._updating = True
            # 主机体
            try:
                p_pos, p_hd, p_el = self._player.sample_at(
                    self._current_time)
                self.spin_p_lat.setValue(self._origin_lat + p_pos.y)
                self.spin_p_lon.setValue(self._origin_lon + p_pos.x)
                self.spin_p_alt.setValue(self._origin_alt + p_pos.z)
                self.spin_p_heading.setValue(p_hd)
                self.spin_p_elev.setValue(p_el)
                self.spin_p_roll.setValue(self._player.roll)
            except Exception:
                pass
            # 当前选中的目标
            idx = self.lst_targets.currentRow()
            if 0 <= idx < len(self._targets):
                t = self._targets[idx]
                try:
                    t_pos, t_hd, t_el = t.sample_at(self._current_time)
                    self.spin_t_lat.setValue(self._origin_lat + t_pos.y)
                    self.spin_t_lon.setValue(self._origin_lon + t_pos.x)
                    self.spin_t_alt.setValue(self._origin_alt + t_pos.z)
                    self.spin_t_heading.setValue(t_hd)
                    self.spin_t_elev.setValue(t_el)
                except Exception:
                    pass
        finally:
            self._updating = False

    def _resimulate_all(self):
        # 主机体：始终按速度运动
        self._player.simulate(self._duration, 0.05)
        # 目标
        for t in self._targets:
            t.simulate(self._duration, 0.05)

        # 同步到画布
        self.canvas.objects = [self._player] + list(self._targets)
        self.canvas.set_duration(self._duration)
        self.canvas.set_time(self._current_time)
        self.canvas.update()

    def _sync_to_flight_data(self):
        """把当前锁定目标反算成 TargetHeading/Elevation/Distance。
        · 只有存在目标且已锁定时才写有效值，且 TargetSelected=1
        · 否则全部清零，TargetSelected=0
        · ★ 位置取当前时间点的实际位置（sample_at）
        """
        t = self.canvas.lock_target
        if t is None:
            try:
                self._fd['TargetHeading'] = 0.0
                self._fd['TargetElevation'] = 0.0
                self._fd['TargetDistance'] = 0.0
                self._fd['TargetSelected'] = 0.0
            except Exception:
                pass
            return
        try:
            p_pos, _, _ = self._player.sample_at(self._current_time)
            t_pos, _, _ = t.sample_at(self._current_time)
        except Exception:
            p_pos = self._player.pos
            t_pos = t.pos
        dx = t_pos.x - p_pos.x   # 东
        dy = t_pos.y - p_pos.y   # 北
        dz = t_pos.z - p_pos.z   # 上
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        if dist > 1e-6:
            hd = math.degrees(math.atan2(dx, dy))
            el = math.degrees(math.asin(max(-1.0, min(1.0, dz / dist))))
        else:
            hd = 0.0
            el = 0.0
        try:
            self._fd['TargetHeading'] = hd
            self._fd['TargetElevation'] = el
            self._fd['TargetDistance'] = dist
            self._fd['TargetSelected'] = 1.0
        except Exception:
            pass

    def _on_canvas_object_picked(self, obj):
        """画布中选中对象 → 同步左侧列表选中（如果是目标）"""
        try:
            if obj is None:
                return
            if getattr(obj, 'is_player', False):
                return
            idx = -1
            for i, t in enumerate(self._targets):
                if t is obj:
                    idx = i
                    break
            if idx < 0:
                return
            self._updating = True
            try:
                self.lst_targets.setCurrentRow(idx)
            finally:
                self._updating = False
            self._load_selected_target_params()
        except Exception:
            pass

    def _on_canvas_objects_changed(self):
        """用户在画布里拖动目标 / 删除目标 / 拖动主机体后同步 UI"""
        # 检测列表与 _targets 是否一致
        visible = [o for o in self.canvas.objects if not o.is_player]
        if len(visible) != len(self._targets):
            self._targets = visible
            self._refresh_target_list()
        # 拖动后同步当前选中目标的数值框
        idx = self.lst_targets.currentRow()
        if 0 <= idx < len(self._targets):
            t = self._targets[idx]
            self._updating = True
            try:
                self.spin_t_lat.setValue(self._origin_lat + t.pos.y)
                self.spin_t_lon.setValue(self._origin_lon + t.pos.x)
                self.spin_t_alt.setValue(self._origin_alt + t.pos.z)
                self.spin_t_heading.setValue(t.heading)
                self.spin_t_elev.setValue(t.elevation)
            finally:
                self._updating = False
        # ★ 同步主机体数据到右侧
        p = self._player
        self._updating = True
        try:
            self.spin_p_lat.setValue(self._origin_lat + p.pos.y)
            self.spin_p_lon.setValue(self._origin_lon + p.pos.x)
            self.spin_p_alt.setValue(self._origin_alt + p.pos.z)
            self.spin_p_heading.setValue(p.heading)
            self.spin_p_elev.setValue(p.elevation)
            self.spin_p_roll.setValue(p.roll)
        finally:
            self._updating = False
        self._resimulate_all()
        self._sync_lock_target()
        self._sync_to_flight_data()
        self.valuesChanged.emit()

    # ============================================================
    #                       外部接口
    # ============================================================

    def refresh_from_data(self):
        """外部（飞行数据窗口 / 工程加载）改动 Target* 后同步显示"""
        if not self._targets:
            return
        hd = float(self._fd.get('TargetHeading', 0.0))
        el = float(self._fd.get('TargetElevation', 0.0))
        dist = float(self._fd.get('TargetDistance', 0.0))
        d = _heading_to_dir(hd, el)
        t = self._targets[0]
        t.heading = hd
        t.elevation = el
        t.pos = _V3(d.x * dist, d.y * dist, d.z * dist)
        self._updating = True
        try:
            self.spin_t_lat.setValue(self._origin_lat + t.pos.y)
            self.spin_t_lon.setValue(self._origin_lon + t.pos.x)
            self.spin_t_alt.setValue(self._origin_alt + t.pos.z)
            self.spin_t_heading.setValue(t.heading)
            self.spin_t_elev.setValue(t.elevation)
        finally:
            self._updating = False
        self._sync_buttons_from_fd()
        self._resimulate_all()

    def closeEvent(self, e):
        try:
            self._timer.stop()
        except Exception:
            pass
        self.closed.emit()
        super().closeEvent(e)


class CustomVarsDialog(QDialog):
    """自定义变量对话框：
    · 玩家可以添加任意名字的变量
    · 变量名与内置变量/函数/其他自定义变量重名时，输入框标红
    · 每个变量带 最小值 / 最大值 / 当前值 / 滑块
    · 修改滑块 → 当前值同步；修改当前值 → 滑块同步
    """
    varsChanged = pyqtSignal()
    closed = pyqtSignal()

    def __init__(self, custom_vars, reserved_provider, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_T('custom_vars_title'))
        self.resize(720, 560)
        self.setWindowFlags(Qt.Window | Qt.WindowSystemMenuHint |
                            Qt.WindowMinMaxButtonsHint |
                            Qt.WindowCloseButtonHint)
        self.setModal(False)
        self._vars = custom_vars          # list[dict]
        self._reserved_provider = reserved_provider
        self._updating = False
        self._row_widgets = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)

        top = QHBoxLayout()
        self.btn_add = QPushButton(_L(u"＋ 添加变量", u"+ Add Variable"))
        self.btn_add.setFixedHeight(26)
        self.btn_add.clicked.connect(self._add_var)
        top.addWidget(self.btn_add)
        top.addStretch(1)
        lay.addLayout(top)

        hint = QLabel(_L(
            u"提示：变量名不能与内置变量、函数名或其他自定义变量重名；"
            u"重名或非法时输入框会标红，且不会被采用。",
            u"Note: names cannot duplicate built-in variables, functions, "
            u"or other custom variables. Invalid/duplicate names are "
            u"highlighted in red and will not be applied."))
        hint.setStyleSheet("color:#666;")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            _L(u"变量名", u"Name"),
            _L(u"最小值", u"Min"),
            _L(u"最大值", u"Max"),
            _L(u"当前值", u"Value"),
            _L(u"滑块", u"Slider"),
            u"",
        ])
        hh = self.table.horizontalHeader()
        for c in (0, 1, 2, 3, 5):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        lay.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        btn_close = QPushButton(_L(u"关闭", u"Close"))
        btn_close.clicked.connect(self.close)
        bottom.addWidget(btn_close)
        lay.addLayout(bottom)

        self._rebuild()

    def _reserved(self):
        try:
            return set(self._reserved_provider())
        except Exception:
            return set()

    def _name_conflict(self, name, exclude_idx):
        name = (name or "").strip()
        if not name:
            return True
        if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', name):
            return True
        if name in self._reserved():
            return True
        for i, d in enumerate(self._vars):
            if i == exclude_idx:
                continue
            if (d.get('name', '') or '') == name:
                return True
        return False

    def _validate_name_widget(self, edit, idx):
        bad = self._name_conflict(edit.text(), idx)
        if bad:
            edit.setStyleSheet(
                "background-color:#ffcccc; border:1px solid #ff0000;")
        else:
            edit.setStyleSheet("")

    def _add_var(self):
        i = 1
        while True:
            cand = u"Var%d" % i
            if not self._name_conflict(cand, -1):
                break
            i += 1
        self._vars.append({'name': cand, 'value': 0.0,
                           'min': -1.0, 'max': 1.0})
        self._rebuild()
        self._emit_change()

    def _del_var(self, idx):
        if 0 <= idx < len(self._vars):
            del self._vars[idx]
        self._rebuild()
        self._emit_change()

    def _rebuild(self):
        self._updating = True
        try:
            n = len(self._vars)
            self.table.setRowCount(n)
            self._row_widgets = []
            for r, d in enumerate(self._vars):
                name = d.get('name', u"")
                lo = float(d.get('min', -1.0))
                hi = float(d.get('max', 1.0))
                val = float(d.get('value', 0.0))

                ne = QLineEdit(name)
                ne.textChanged.connect(
                    lambda _, rr=r, e=ne: self._validate_name_widget(e, rr))
                ne.editingFinished.connect(
                    lambda rr=r, e=ne: self._commit_name(rr, e))
                self.table.setCellWidget(r, 0, ne)

                mn = QDoubleSpinBox()
                mn.setRange(-1e9, 1e9); mn.setDecimals(1)
                mn.setSingleStep(0.1)
                mn.setKeyboardTracking(False); mn.setValue(round(lo, 1))
                mn.valueChanged.connect(
                    lambda v, rr=r: self._on_range_changed(rr, 'min', v))
                self.table.setCellWidget(r, 1, mn)

                mx = QDoubleSpinBox()
                mx.setRange(-1e9, 1e9); mx.setDecimals(1)
                mx.setSingleStep(0.1)
                mx.setKeyboardTracking(False); mx.setValue(round(hi, 1))
                mx.valueChanged.connect(
                    lambda v, rr=r: self._on_range_changed(rr, 'max', v))
                self.table.setCellWidget(r, 2, mx)

                vs = QDoubleSpinBox()
                vs.setRange(-1e9, 1e9); vs.setDecimals(4)
                vs.setKeyboardTracking(False); vs.setValue(val)
                vs.valueChanged.connect(
                    lambda v, rr=r: self._on_value_changed(rr, v))
                self.table.setCellWidget(r, 3, vs)

                sw = QWidget()
                sl = QHBoxLayout(sw)
                sl.setContentsMargins(0, 0, 0, 0); sl.setSpacing(4)
                slider = QSlider(Qt.Horizontal)
                slider.setRange(0, 10000)
                slider.setValue(self._value_to_slider(val, lo, hi))
                slider.valueChanged.connect(
                    lambda v, rr=r: self._on_slider_changed(rr, v))
                sl.addWidget(slider, 1)
                self.table.setCellWidget(r, 4, sw)

                bd = QPushButton(u"🗑")
                bd.setFixedWidth(30); bd.setFixedHeight(22)
                bd.clicked.connect(lambda _, rr=r: self._del_var(rr))
                self.table.setCellWidget(r, 5, bd)

                self._row_widgets.append(
                    {'name': ne, 'min': mn, 'max': mx, 'value': vs,
                     'slider': slider})
                self._validate_name_widget(ne, r)
        finally:
            self._updating = False

    @staticmethod
    def _value_to_slider(v, lo, hi):
        if hi - lo < 1e-9:
            return 5000
        t = (v - lo) / (hi - lo)
        return max(0, min(10000, int(round(t * 10000))))

    @staticmethod
    def _slider_to_value(s, lo, hi):
        if hi - lo < 1e-9:
            return lo
        return lo + (hi - lo) * s / 10000.0

    def _commit_name(self, idx, edit):
        if self._updating: return
        new_name = edit.text().strip()
        if self._name_conflict(new_name, idx):
            # ★ 非法/重名 → 回滚到原名字
            old = (self._vars[idx].get('name', u"")
                   if 0 <= idx < len(self._vars) else u"")
            self._updating = True
            try:
                edit.setText(old)
            finally:
                self._updating = False
            self._validate_name_widget(edit, idx)
            return
        if 0 <= idx < len(self._vars):
            if self._vars[idx].get('name') == new_name:
                return
            self._vars[idx]['name'] = new_name
            self._emit_change()

    def _on_range_changed(self, idx, key, v):
        if self._updating: return
        if not (0 <= idx < len(self._vars)): return
        d = self._vars[idx]
        d[key] = float(v)
        lo = float(d.get('min', -1.0))
        hi = float(d.get('max', 1.0))
        if hi < lo:
            lo, hi = hi, lo
            d['min'] = lo; d['max'] = hi
        cur = float(d.get('value', 0.0))
        cur = max(lo, min(hi, cur))
        d['value'] = cur
        w = self._row_widgets[idx] if idx < len(self._row_widgets) else None
        if w:
            self._updating = True
            try:
                w['value'].setValue(cur)
                w['slider'].setValue(self._value_to_slider(cur, lo, hi))
            finally:
                self._updating = False
        self._emit_change()

    def _on_value_changed(self, idx, v):
        if self._updating: return
        if not (0 <= idx < len(self._vars)): return
        d = self._vars[idx]
        lo = float(d.get('min', -1.0))
        hi = float(d.get('max', 1.0))
        v = max(lo, min(hi, float(v)))
        d['value'] = v
        w = self._row_widgets[idx] if idx < len(self._row_widgets) else None
        if w:
            self._updating = True
            try:
                if abs(w['value'].value() - v) > 1e-9:
                    w['value'].setValue(v)
                w['slider'].setValue(self._value_to_slider(v, lo, hi))
            finally:
                self._updating = False
        self._emit_change()

    def _on_slider_changed(self, idx, s):
        if self._updating: return
        if not (0 <= idx < len(self._vars)): return
        d = self._vars[idx]
        lo = float(d.get('min', -1.0))
        hi = float(d.get('max', 1.0))
        v = self._slider_to_value(s, lo, hi)
        d['value'] = v
        w = self._row_widgets[idx] if idx < len(self._row_widgets) else None
        if w:
            self._updating = True
            try:
                w['value'].setValue(v)
            finally:
                self._updating = False
        self._emit_change()

    def _emit_change(self):
        try:
            self.varsChanged.emit()
        except Exception:
            pass

    def closeEvent(self, e):
        self.closed.emit()
        super().closeEvent(e)


class SaveSettingsDialog(QDialog):
    """保存设置对话框：
    · 勾选“启用设置保存”并选好路径 → 确定后立即写入，并开启自动保存
    · 取消勾选 → 关闭设置保存
    · 若目标文件已存在 → 询问覆盖 / 沿用
    · 直接关闭窗口 → 不做任何操作
    """
    def __init__(self, enabled, path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_L(u"保存设置", u"Save Settings"))
        self.setFixedWidth(560)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._result_enabled = bool(enabled)
        self._result_path = path or u""
        self._result_overwrite = False

        v = QVBoxLayout(self)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(10)

        hint = QLabel(_L(
            u"设置文件用于自动保存当前窗口的状态、各项设置和编辑未保存\n"
            u"的内容。启用后每次编辑会自动写入该文件。",
            u"The settings file auto-saves the current window state,\n"
            u"all settings, and unsaved edits. Once enabled, every edit\n"
            u"will be written to this file automatically."))
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#555;")
        v.addWidget(hint)

        self.chk_enable = QCheckBox(_L(u"启用设置保存",
                                       u"Enable settings saving"))
        self.chk_enable.setChecked(bool(enabled))
        v.addWidget(self.chk_enable)

        path_row = QHBoxLayout()
        path_row.setSpacing(6)
        self.edit_path = QLineEdit(self._result_path)
        self.edit_path.setPlaceholderText(
            _L(u"选择存放设置文件的路径…",
               u"Choose a path for the settings file…"))
        self.btn_browse = QPushButton(_L(u"浏览…", u"Browse…"))
        self.btn_browse.setFixedWidth(70)
        path_row.addWidget(self.edit_path, 1)
        path_row.addWidget(self.btn_browse)
        v.addLayout(path_row)

        v.addStretch(1)

        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton(_L(u"确定", u"OK"))
        cancel = QPushButton(_L(u"取消", u"Cancel"))
        ok.setFixedHeight(26); cancel.setFixedHeight(26)
        ok.setDefault(True)
        row.addWidget(ok); row.addWidget(cancel)
        v.addLayout(row)

        self.btn_browse.clicked.connect(self._browse)
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        self.chk_enable.toggled.connect(self._update_enabled_state)
        self._update_enabled_state()

    def _update_enabled_state(self):
        on = self.chk_enable.isChecked()
        self.edit_path.setEnabled(on)
        self.btn_browse.setEnabled(on)

    def _browse(self):
        path, _ = QFileDialog.getSaveFileName(
            self, _L(u"选择设置文件", u"Choose settings file"),
            self.edit_path.text() or u"settings.json",
            u"JSON (*.json)")
        if path:
            self.edit_path.setText(path)

    def accept(self):
        # 未启用 → 直接关闭设置保存
        if not self.chk_enable.isChecked():
            self._result_enabled = False
            self._result_path = u""
            super().accept()
            return
        path = self.edit_path.text().strip()
        if not path:
            QMessageBox.warning(
                self, _L(u"提示", u"Info"),
                _L(u"请选择设置文件路径",
                   u"Please choose a settings file path"))
            return
        overwrite = True
        if os.path.exists(path):
            r = QMessageBox.question(
                self, _L(u"文件已存在", u"File already exists"),
                _L(u"该路径下已有一份设置文件：\n%s\n\n"
                   u"是：覆盖（用当前状态写入）\n"
                   u"否：沿用（保留原文件，不写入）\n"
                   u"取消：返回修改",
                   u"A settings file already exists at:\n%s\n\n"
                   u"Yes: Overwrite (write current state)\n"
                   u"No: Keep existing (do not write)\n"
                   u"Cancel: Go back") % path,
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes)
            if r == QMessageBox.Cancel:
                return
            if r == QMessageBox.No:
                overwrite = False
        self._result_enabled = True
        self._result_path = path
        self._result_overwrite = overwrite
        super().accept()


class _MultiInputDialog(QDialog):
    def __init__(self, title, fields, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        v = QVBoxLayout(self)
        f = QFormLayout()
        self.edits = []
        self.kinds = []
        for spec in fields:
            if len(spec) == 3:
                label, default, kind = spec
            else:
                label, default = spec
                kind = "line"
            if kind == "check":
                e = QCheckBox()
                e.setChecked(default in (True, 1, "1", "true"))
            else:
                e = QLineEdit(str(default))
            f.addRow(label, e)
            self.edits.append(e)
            self.kinds.append(kind)
        v.addLayout(f)
        row = QHBoxLayout();
        row.addStretch(1)
        ok = QPushButton(u"确定");
        cc = QPushButton(u"取消")
        row.addWidget(ok);
        row.addWidget(cc)
        v.addLayout(row)
        ok.clicked.connect(self.accept)
        cc.clicked.connect(self.reject)

    def values(self):
        out = []
        for e, k in zip(self.edits, self.kinds):
            if k == "check":
                out.append("1" if e.isChecked() else "0")
            else:
                out.append(e.text().strip())
        return out


class PropertyPanel(QScrollArea):
    addCharRequested = pyqtSignal()
    compensateToggled = pyqtSignal(bool)

    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self._updating = False
        self._bind_pick_children = []
        self.setWidgetResizable(True)
        self.setMinimumWidth(300)
        inner = QWidget();
        self.setWidget(inner)
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(10, 10, 10, 10);
        lay.setSpacing(8)

        gb1 = QGroupBox(_T('content'))
        self._refs_gb1 = gb1
        v1 = QVBoxLayout(gb1)
        self.text_edit = QLineEdit()
        self.text_edit.setPlaceholderText(_L(
            u"输入字符，或用 {表达式} 求值",
            u"Enter text, or {expression} to evaluate"))
        self._text_edit_completer = _AutoCompleter(
            self.text_edit, _all_words)
        v1.addWidget(self.text_edit)
        pv = QHBoxLayout()
        self._lbl_preview = QLabel(_T('preview'))
        pv.addWidget(self._lbl_preview)
        self.preview_label = QLabel(u"—")
        self.preview_label.setStyleSheet(
            "color: #0066cc; background: #f5f5f5; padding: 2px; border-radius: 3px;")
        self.preview_label.setWordWrap(True)
        self.preview_label.setMinimumHeight(20)
        pv.addWidget(self.preview_label, 1)
        v1.addLayout(pv)

        btn_row = QHBoxLayout()
        self.btn_insert_var = QToolButton()
        self.btn_insert_var.setText(_T('insert_var'))
        self.btn_insert_var.setPopupMode(QToolButton.InstantPopup)
        self._custom_var_names = []
        self._rebuild_insert_var_menu()
        btn_row.addWidget(self.btn_insert_var)

        self.btn_insert_fn = QToolButton()
        self.btn_insert_fn.setText(_T('insert_fn'))
        self.btn_insert_fn.setPopupMode(QToolButton.InstantPopup)
        fm = QMenu(self.btn_insert_fn)
        FNS = [u"abs(x)", u"ceil(x)", u"clamp(x,min,max)", u"clamp01(x)",
               u"deltaangle(a,b)", u"exp(x)", u"floor(x)",
               u"inverselerp(a,b,x)", u"lerp(a,b,t)", u"lerpangle(a,b,t)",
               u"lerpunclamped(a,b,t)", u"log(x,p)", u"log10(x)",
               u"pingpong(x,l)", u"max(a,b)", u"min(a,b)",
               u"pow(x,p)", u"repeat(x,l)", u"round(x)", u"sign(x)",
               u"smoothstep(a,b,t)", u"sqrt(x)", u"sin(x)", u"cos(x)",
               u"tan(x)", u"asin(x)", u"acos(x)", u"atan(x)", u"atan2(y,x)",
               u"sum(x)", u"rate(x)", u"smooth(x,r)", u"PID(t,c,p,i,d)",
               u"a?b:c"]
        for fn in FNS:
            a = fm.addAction(fn)
            a.triggered.connect(lambda c=False, s=fn: self._insert_text(u"{%s}" % s))
        self.btn_insert_fn.setMenu(fm)
        btn_row.addWidget(self.btn_insert_fn)

        # ---- 插入预设 ----
        self.btn_insert_preset = QToolButton()
        self.btn_insert_preset.setText(_T('insert_preset'))
        self.btn_insert_preset.setPopupMode(QToolButton.InstantPopup)
        self._rebuild_insert_preset_menu()
        btn_row.addWidget(self.btn_insert_preset)

        # ---- 添加字符 ----
        self.btn_add_char_quick = QPushButton(_T('add_char_btn'))
        self.btn_add_char_quick.setFixedHeight(22)
        self.btn_add_char_quick.setMinimumWidth(80)
        self.btn_add_char_quick.clicked.connect(self.addCharRequested.emit)
        btn_row.addWidget(self.btn_add_char_quick)

        # ★ 补偿偏移开关
        self.chk_compensate = QPushButton(_L(u"补偿偏移", u"Offset Comp"))
        self.chk_compensate.setCheckable(True)
        self.chk_compensate.setFixedHeight(22)
        self.chk_compensate.setToolTip(_L(
            u"开启后：当使用 FunkyTree 函数时，自动添加字符偏移补偿公式",
            u"When ON: automatically adds glyph offset compensation\n"
            u"when using FunkyTree expressions"))
        self.chk_compensate.toggled.connect(self.compensateToggled.emit)
        btn_row.addWidget(self.chk_compensate)

        btn_row.addStretch(1)
        v1.addLayout(btn_row)

        # ---- 富文本快捷标签 ----
        tag_row = QHBoxLayout()
        tag_row.setSpacing(4)
        self._tag_open_state = {'alpha': False, 'mark': False}

        def _mk_tag_btn(label, insert_str, tip=None):
            b = QPushButton(label)
            b.setFixedHeight(22)
            if tip: b.setToolTip(tip)
            b.clicked.connect(lambda: self._insert_text(insert_str))
            tag_row.addWidget(b)
            return b

        # <color> 已移除（颜色按钮已提供选色功能）

        self.btn_alpha_tag = QPushButton(u"<alpha>")
        self.btn_alpha_tag.setFixedHeight(22)
        self.btn_alpha_tag.setToolTip(_L(
            u"透明度标签（点击两次切换）\n"
            u"第一次：<alpha=#80>\n"
            u"第二次：<alpha=#FF>",
            u"Alpha tag (two-click toggle)\n"
            u"1st click: <alpha=#80>\n"
            u"2nd click: <alpha=#FF>"))
        self.btn_alpha_tag.clicked.connect(self._on_alpha_tag_clicked)
        tag_row.addWidget(self.btn_alpha_tag)

        self.btn_mark_tag = QPushButton(u"<mark>")
        self.btn_mark_tag.setFixedHeight(22)
        self.btn_mark_tag.setToolTip(_L(
            u"背景色标签（点击两次成对插入）\n"
            u"第一次：<mark=#FFFF00>\n"
            u"第二次：</mark>",
            u"Mark tag (two-click pair insert)\n"
            u"1st click: <mark=#FFFF00>\n"
            u"2nd click: </mark>"))
        self.btn_mark_tag.clicked.connect(self._on_mark_tag_clicked)
        tag_row.addWidget(self.btn_mark_tag)

        _mk_tag_btn(u"<br>", u"<br>", _L(u"强制换行", u"Line break"))
        _mk_tag_btn(u"<space>", u"<space=4>",
                    _L(u"可控空格", u"Controlled space"))
        tag_row.addStretch(1)
        v1.addLayout(tag_row)

        lay.addWidget(gb1)

        # ---- 样式 ----
        gb2 = QGroupBox(_T('style'))
        self._refs_gb2 = gb2
        f2 = QFormLayout(gb2)

        # size 行
        size_row = QWidget()
        srl = QHBoxLayout(size_row)
        srl.setContentsMargins(0, 0, 0, 0);
        srl.setSpacing(4)
        self.size_spin = SizeSpinBox()
        self.chk_size_expr = QCheckBox(u"fx")
        self.chk_size_expr.setToolTip(_L(
            u"勾选则输出 size 函数栏的内容",
            u"When checked, output the size expression field"))
        self.size_expr_edit = FnLineEdit(u"FunkyTree")
        srl.addWidget(self.size_spin)
        srl.addWidget(self.chk_size_expr)
        srl.addWidget(self.size_expr_edit, 1)
        self._lbl_size = QLabel(_T('char_size'))
        f2.addRow(self._lbl_size, size_row)

        # rotate 行
        rot_row = QWidget()
        rrl = QHBoxLayout(rot_row)
        rrl.setContentsMargins(0, 0, 0, 0);
        rrl.setSpacing(4)
        self.rot_spin = PosVOSpinBox()
        self.rot_spin.setRange(-9999.0, 9999.0)
        self.rot_spin.setSuffix(u" °")
        self.rot_spin.setFixedWidth(78)
        self.chk_rot_expr = QCheckBox(u"fx")
        self.chk_rot_expr.setToolTip(_L(
            u"勾选则输出 rotate 函数栏的内容",
            u"When checked, output the rotate expression field"))
        self.rot_expr_edit = FnLineEdit(u"FunkyTree")
        rrl.addWidget(self.rot_spin)
        rrl.addWidget(self.chk_rot_expr)
        rrl.addWidget(self.rot_expr_edit, 1)
        self._lbl_rot = QLabel(_T('rotate'))
        f2.addRow(self._lbl_rot, rot_row)

        # B I U S 一行
        row = QWidget();
        h = QHBoxLayout(row);
        h.setContentsMargins(0, 0, 0, 0);
        h.setSpacing(2)
        self.bold_btn = QPushButton(u"B");
        self.bold_btn.setCheckable(True)
        self.bold_btn.setFixedWidth(32)
        fb = self.bold_btn.font();
        fb.setBold(True);
        self.bold_btn.setFont(fb)
        self.italic_btn = QPushButton(u"I");
        self.italic_btn.setCheckable(True)
        self.italic_btn.setFixedWidth(32)
        fi = self.italic_btn.font();
        fi.setItalic(True);
        self.italic_btn.setFont(fi)
        self.underline_btn = QPushButton(u"U");
        self.underline_btn.setCheckable(True)
        self.underline_btn.setFixedWidth(32)
        fu = self.underline_btn.font();
        fu.setUnderline(True);
        self.underline_btn.setFont(fu)
        self.strike_btn = QPushButton(u"S");
        self.strike_btn.setCheckable(True)
        self.strike_btn.setFixedWidth(32)
        fs = self.strike_btn.font();
        fs.setStrikeOut(True);
        self.strike_btn.setFont(fs)
        h.addWidget(self.bold_btn);
        h.addWidget(self.italic_btn)
        h.addWidget(self.underline_btn);
        h.addWidget(self.strike_btn)
        h.addStretch(1)
        self._lbl_bi = QLabel(_T('bold_italic'))
        f2.addRow(self._lbl_bi, row)

        self.color_btn = QPushButton(_L(
            u"文字颜色（默认 #000000）",
            u"Color (default #000000)"))
        self.color_btn.setFixedHeight(28)
        self._lbl_color = QLabel(_T('color'))
        f2.addRow(self._lbl_color, self.color_btn)
        lay.addWidget(gb2)

        # ---- 坐标 ----
        gb3 = QGroupBox(_T('coords'))
        self._refs_gb3 = gb3
        f3 = QFormLayout(gb3)

        pos_row = QWidget()
        prl = QHBoxLayout(pos_row)
        prl.setContentsMargins(0, 0, 0, 0);
        prl.setSpacing(4)
        self.pos_spin = PosVOSpinBox()
        self.pos_spin.setRange(-99999.0, 99999.0)
        self.pos_spin.setFixedWidth(78)
        self.chk_pos_expr = QCheckBox(u"fx")
        self.chk_pos_expr.setToolTip(_L(
            u"勾选则输出 pos 函数栏的内容",
            u"When checked, output the pos expression field"))
        self.pos_expr_edit = FnLineEdit(u"FunkyTree")
        prl.addWidget(self.pos_spin)
        prl.addWidget(self.chk_pos_expr)
        prl.addWidget(self.pos_expr_edit, 1)
        self._lbl_pos = QLabel(_T('pos'))
        f3.addRow(self._lbl_pos, pos_row)

        vo_row = QWidget()
        vrl = QHBoxLayout(vo_row)
        vrl.setContentsMargins(0, 0, 0, 0);
        vrl.setSpacing(4)
        self.vo_spin = PosVOSpinBox()
        self.vo_spin.setRange(-99999.0, 99999.0)
        self.vo_spin.setFixedWidth(78)
        self.chk_vo_expr = QCheckBox(u"fx")
        self.chk_vo_expr.setToolTip(_L(
            u"勾选则输出 voffset 函数栏的内容",
            u"When checked, output the voffset expression field"))
        self.vo_expr_edit = FnLineEdit(u"FunkyTree")
        vrl.addWidget(self.vo_spin)
        vrl.addWidget(self.chk_vo_expr)
        vrl.addWidget(self.vo_expr_edit, 1)
        self._lbl_vo = QLabel(_T('voffset'))
        f3.addRow(self._lbl_vo, vo_row)

        lay.addWidget(gb3)
        self.gb_helpers = QGroupBox(_T('helpers_menu'))
        vh = QVBoxLayout(self.gb_helpers)
        row_h = QHBoxLayout()
        row_h.setSpacing(4)
        self.btn_tool_point = QPushButton(_T('point_lbl'))
        self.btn_tool_point.setCheckable(True)
        self.btn_tool_line = QPushButton(_T('line_lbl'))
        self.btn_tool_line.setCheckable(True)
        self.btn_tool_circle = QPushButton(_T('circle_lbl'))
        self.btn_tool_circle.setCheckable(True)
        for b in (self.btn_tool_point, self.btn_tool_line, self.btn_tool_circle):
            b.setFixedHeight(24)
            row_h.addWidget(b)
        vh.addLayout(row_h)

        row_h2 = QHBoxLayout()
        row_h2.setSpacing(4)
        self.btn_snap_grid = QPushButton(_T('snap_grid'))
        self.btn_snap_grid.setCheckable(True)
        self.btn_snap_grid.setChecked(True)
        self.btn_snap_helpers = QPushButton(_T('char_snap'))
        self.btn_snap_helpers.setCheckable(True)
        self.btn_snap_helpers.setChecked(True)
        self.btn_lock_helpers = QPushButton(_T('lock_helpers'))
        self.btn_lock_helpers.setCheckable(True)
        for b in (self.btn_snap_grid, self.btn_snap_helpers, self.btn_lock_helpers):
            b.setFixedHeight(24)
            row_h2.addWidget(b)
        vh.addLayout(row_h2)

        row_h3 = QHBoxLayout()
        row_h3.setSpacing(4)
        self.btn_bind = QPushButton(_T('bind_btn'))
        self.btn_bind.setCheckable(True)
        self.btn_bind.setToolTip(_L(
            u"点此开启吸附模式：\n先点一个对象（字符/辅助），再点另一个，完成吸附",
            u"Click to enable binding mode:\nclick one object (char/helper), then another, to complete binding"))
        self.btn_unbind = QPushButton(_T('unbind_btn'))
        self.btn_unbind_all = QPushButton(_T('unbind_all_btn'))
        for b in (self.btn_bind, self.btn_unbind, self.btn_unbind_all):
            b.setFixedHeight(24)
            row_h3.addWidget(b)
        vh.addLayout(row_h3)

        lay.addWidget(self.gb_helpers)
        lay.addStretch(1)

        self._widgets = [self.text_edit, self.size_spin, self.rot_spin,
                         self.bold_btn, self.italic_btn,
                         self.underline_btn, self.strike_btn,
                         self.color_btn,
                         self.pos_spin, self.vo_spin,
                         self.chk_pos_expr, self.pos_expr_edit,
                         self.chk_vo_expr, self.vo_expr_edit,
                         self.chk_size_expr, self.size_expr_edit,
                         self.chk_rot_expr, self.rot_expr_edit]
        self._set_color_btn(self.color_btn, DEFAULT_COLOR)
        self._connect();
        self.refresh_ranges();
        self.refresh()

    def _insert_text(self, s):
        # ★ 未选中任何字符 → 先自动新建一个字符
        #   （MainWindow.add_char 会同步创建 RichItem、把它选中、
        #    把焦点移到文本栏并全选默认文本"文本"；
        #    随后的 insert 会替换掉这段默认文本 → 新字符内容即预设内容）
        try:
            if not self.canvas.selected:
                self.addCharRequested.emit()
        except Exception:
            pass
        # ★ 在光标处插入（不再追加到末尾）
        self.text_edit.insert(s)
        self.text_edit.setFocus()

    def _rebuild_insert_preset_menu(self):
        """重建「插入预设」菜单：
        · 菜单文字按当前语言生成
        · 插入内容里的占位文字也按语言选（中文"文字" / 英文"Text"）
        · 切换语言时调用，避免中文残留
        """
        placeholder = _L(u"文字", u"Text")
        PRESETS = [
            (_L(u"油门读数", u"Throttle Readout"),
             u"{Throttle*100;0.0}%"),
            (_L(u"时间累加", u"Time Sum"),
             u"{sum(1);0.0}"),
            (_L(u"正弦波动", u"Sine Wave"),
             u"{sin(Time*60)*10;0.00}"),
            (_L(u"乒乓往复", u"Pingpong"),
             u"{pingpong(Time,5);0.0}"),
            (_L(u"条件颜色", u"Conditional Color"),
             u'<color={Activate1>0?"#FF0000":"#000000"}>%s</color>'
             % placeholder),
            (_L(u"按键缩放", u"Key Size"),
             u"<size={1+clamp01(Activate1)}>%s</size>" % placeholder),
            (_L(u"横向飘动", u"Horizontal Drift"),
             u"<pos={sin(Time*60)*5}>%s</pos>" % placeholder),
            (_L(u"垂直浮动", u"Vertical Float"),
             u"<voffset={sin(Time*60)*5}>%s</voffset>" % placeholder),
        ]
        pm = QMenu(self.btn_insert_preset)
        for name, s in PRESETS:
            a = pm.addAction(name)
            a.triggered.connect(lambda c=False, t=s: self._insert_text(t))
        # ★ 已移除「沿辅助圆旋转 / 沿辅助线滑动」两项预设入口
        #   （功能有设计缺陷；如需恢复，取消下面两段的注释即可）
        # a_orbit = pm.addAction(
        #     _L(u"沿辅助圆旋转", u"Rotate on Helper Circle"))
        # a_orbit.triggered.connect(self._insert_orbit_circle)
        # a_slide = pm.addAction(
        #     _L(u"沿辅助线滑动", u"Slide on Helper Line"))
        # a_slide.triggered.connect(self._insert_slide_line)
        old = self.btn_insert_preset.menu()
        self.btn_insert_preset.setMenu(pm)
        if old is not None:
            try:
                old.deleteLater()
            except Exception:
                pass

    def _on_alpha_tag_clicked(self):
        # ★ 用 <alpha=#FF> 恢复不透明
        t = self.text_edit.text() or u""
        if _unclosed_count(t, 'alpha') > 0:
            self._insert_text(u"<alpha=#FF>")
        else:
            self._insert_text(u"<alpha=#80>")

    def _on_mark_tag_clicked(self):
        # ★ 根据当前 text_edit 内容动态判断：已开 → 关，未开 → 开
        t = self.text_edit.text() or u""
        if _unclosed_count(t, 'mark') > 0:
            self._insert_text(u"</mark>")
        else:
            self._insert_text(u"<mark=#FFFF00>")

    def _rebuild_insert_var_menu(self):
        """重建「插入变量」菜单（含玩家自定义变量）"""
        vm = QMenu(self.btn_insert_var)
        for name in CONTROL_VARS:
            a = vm.addAction(name)
            a.triggered.connect(
                lambda c=False, n=name: self._insert_text(u"{%s}" % n))
        vm.addSeparator()
        for name in FLIGHT_VARS:
            if name == 'Heading': continue
            a = vm.addAction(name)
            a.triggered.connect(
                lambda c=False, n=name: self._insert_text(u"{%s}" % n))
        vm.addSeparator()
        # ★ 自定义变量（在主菜单底部单列一段）
        if getattr(self, '_custom_var_names', None):
            for name in self._custom_var_names:
                a = vm.addAction(u"★ " + name)
                a.triggered.connect(
                    lambda c=False, n=name: self._insert_text(u"{%s}" % n))
            vm.addSeparator()
        for n2 in ('pi', 'e'):
            a = vm.addAction(n2)
            a.triggered.connect(
                lambda c=False, n=n2: self._insert_text(u"{%s}" % n))
        old = self.btn_insert_var.menu()
        self.btn_insert_var.setMenu(vm)
        if old is not None:
            try:
                old.deleteLater()
            except Exception:
                pass

    def set_custom_var_names(self, names):
        """由主窗口调用：把当前自定义变量名同步到「插入变量」菜单"""
        self._custom_var_names = list(names or [])
        self._rebuild_insert_var_menu()

    # ---- 沿辅助圆旋转 ----
    def _insert_orbit_circle(self):
        ctrl, ok = QInputDialog.getText(
            self, _L(u"沿辅助圆旋转", u"Rotate on Helper Circle"),
            _L(u"控制变量（0~1 绕一圈）：",
               u"Control variable (0~1 for full turn):"),
            text=u"Activate1")
        if not ok or not ctrl.strip(): return
        ctrl = ctrl.strip()

        target = None
        for obj in self.canvas.selected_helpers:
            if isinstance(obj, HelperCircle):
                target = obj;
                break
        if target is None and self.canvas.helper_circles:
            target = self.canvas.helper_circles[0]
        if target is None:
            QMessageBox.information(
                self, _T('hint'),
                _L(u"画布上没有辅助圆", u"No helper circle on canvas"))
            return
        sel = self.canvas.selected
        if not sel:
            QMessageBox.information(self, _T('hint'), _T('no_selection'))
            return

        cx = target.point.x
        cy = target.point.y
        r = target.radius

        # ★ 顶部=0°（逆时针为正）：
        #   pos_w = cx - r·sin(θ),  y_w = cy - r·cos(θ)
        #   输出：pos = cx·20 - r·20·sin(θ)
        #         vo  = -cy·10 + r·10·cos(θ)
        pos_expr = u"%s-%s*sin((%s)*360)" % (
            _fmt(cx * POS_PER_WORLD),
            _fmt(r * POS_PER_WORLD),
            ctrl)
        vo_expr = u"%s+%s*cos((%s)*360)" % (
            _fmt(-cy * VO_PER_WORLD),
            _fmt(r * VO_PER_WORLD),
            ctrl)

        self._write_pos_vo(pos_expr, vo_expr)

    # ---- 沿辅助线滑动 ----
    def _insert_slide_line(self):
        ctrl, ok = QInputDialog.getText(
            self, _L(u"沿辅助线滑动", u"Slide on Helper Line"),
            _L(u"控制变量（0=起点, 1=终点）：",
               u"Control variable (0=start, 1=end):"),
            text=u"Activate1")
        if not ok or not ctrl.strip(): return
        ctrl = ctrl.strip()

        target = None
        for obj in self.canvas.selected_helpers:
            if isinstance(obj, HelperLine):
                target = obj;
                break
        if target is None and self.canvas.helper_lines:
            target = self.canvas.helper_lines[0]
        if target is None:
            QMessageBox.information(
                self, _T('hint'),
                _L(u"画布上没有辅助线", u"No helper line on canvas"))
            return
        sel = self.canvas.selected
        if not sel:
            QMessageBox.information(self, _T('hint'), _T('no_selection'))
            return

        x1, y1 = target.x1, target.y1
        x2, y2 = target.x2, target.y2
        dx = x2 - x1;
        dy = y2 - y1

        # 世界坐标：pos_w = x1 + dx·t,  y_w = y1 + dy·t
        # 输出值：  pos   = pos_w · 20, vo  = -y_w · 10
        pos_expr = u"%s+%s*(%s)" % (
            _fmt(x1 * POS_PER_WORLD),
            _fmt(dx * POS_PER_WORLD),
            ctrl)
        vo_expr = u"%s-%s*(%s)" % (
            _fmt(-y1 * VO_PER_WORLD),
            _fmt(dy * VO_PER_WORLD),
            ctrl)

        self._write_pos_vo(pos_expr, vo_expr)

    # ---- 写入 pos/vo 函数栏 ----
    def _write_pos_vo(self, pos_expr, vo_expr):
        sel = self.canvas.selected
        for it in sel:
            it.custom_pos_expr = pos_expr
            it.custom_pos_enabled = True
            it.custom_vo_expr = vo_expr
            it.custom_vo_enabled = True

        # 同步面板控件（阻断信号，避免触发 _apply 二次写）
        self._updating = True
        it = sel[0]
        self.chk_pos_expr.setChecked(True)
        self.pos_expr_edit.setPlainText(it.custom_pos_expr)
        self.chk_vo_expr.setChecked(True)
        self.vo_expr_edit.setPlainText(it.custom_vo_expr)
        self._updating = False

        self.canvas.eval_all(0.0)
        self.canvas.update()
        self.canvas.contentChanged.emit()
        self._update_preview()

    @staticmethod
    def _set_color_btn(btn, color):
        btn.color_value = QColor(color)
        btn.setStyleSheet(
            "background-color:%s;border:1px solid #888;border-radius:3px;color:%s;"
            % (color.name(), "#ffffff" if color.lightness() < 128 else "#000000"))

    def _apply(self, fn):
        if self._updating: return
        sel = list(self.canvas.selected) + list(self.canvas.selected_helpers)
        if not sel: return
        for it in sel:
            try:
                fn(it)
            except Exception:
                pass
        self.canvas.eval_all(0.0)
        self.canvas.update()
        self.canvas.contentChanged.emit()

    def _connect(self):
        self.text_edit.textChanged.connect(self._on_text)
        self.size_spin.valueChanged.connect(self._on_size)

        def on_rot(v):
            self._apply(lambda it: setattr(it, "rotation", float(v)))
        self.rot_spin.valueChanged.connect(on_rot)
        self.bold_btn.toggled.connect(
            lambda v: self._apply(lambda it: setattr(it, "bold", bool(v))))
        self.italic_btn.toggled.connect(
            lambda v: self._apply(lambda it: setattr(it, "italic", bool(v))))
        self.underline_btn.toggled.connect(
            lambda v: self._apply(lambda it: setattr(it, "underline", bool(v))))
        self.strike_btn.toggled.connect(
            lambda v: self._apply(lambda it: setattr(it, "strike", bool(v))))
        self.color_btn.clicked.connect(self._on_color)

        def on_pos(v):
            w = float(v) / POS_PER_WORLD
            w = max(-self.canvas.x_half(), min(self.canvas.x_half(), w))

            def _set_x(it):
                if isinstance(it, RichItem):
                    it.x = w
                elif isinstance(it, HelperPoint):
                    it.x = w
                    it.use_expr_x = False
                elif isinstance(it, HelperCircle):
                    if it.point is not None:
                        it.point.x = w
                        it.point.use_expr_x = False
                elif isinstance(it, HelperLine):
                    cx = (it.dx1() + it.dx2()) / 2.0
                    dx = w - cx
                    it.x1 += dx; it.x2 += dx
                    it.use_expr_x1 = False
                    it.use_expr_x2 = False
            self._apply(_set_x)

        def on_vo(v):
            w = -float(v) / VO_PER_WORLD
            w = max(-self.canvas.y_half(), min(self.canvas.y_half(), w))

            def _set_y(it):
                if isinstance(it, RichItem):
                    it.y = w
                elif isinstance(it, HelperPoint):
                    it.y = w
                    it.use_expr_y = False
                elif isinstance(it, HelperCircle):
                    if it.point is not None:
                        it.point.y = w
                        it.point.use_expr_y = False
                elif isinstance(it, HelperLine):
                    cy = (it.dy1() + it.dy2()) / 2.0
                    dy = w - cy
                    it.y1 += dy; it.y2 += dy
                    it.use_expr_y1 = False
                    it.use_expr_y2 = False
            self._apply(_set_y)

        self.pos_spin.valueChanged.connect(on_pos)
        self.vo_spin.valueChanged.connect(on_vo)
        self.pos_expr_edit.textChanged.connect(self._on_pos_expr)
        self.vo_expr_edit.textChanged.connect(self._on_vo_expr)
        self.chk_pos_expr.toggled.connect(self._on_pos_expr_toggle)
        self.chk_vo_expr.toggled.connect(self._on_vo_expr_toggle)
        self.size_expr_edit.textChanged.connect(self._on_size_expr)
        self.rot_expr_edit.textChanged.connect(self._on_rot_expr)
        self.chk_size_expr.toggled.connect(self._on_size_expr_toggle)
        self.chk_rot_expr.toggled.connect(self._on_rot_expr_toggle)

        self.btn_tool_point.toggled.connect(lambda v: self._set_tool('point', v))
        self.btn_tool_line.toggled.connect(lambda v: self._set_tool('line', v))
        self.btn_tool_circle.toggled.connect(lambda v: self._set_tool('circle', v))
        self.btn_snap_grid.toggled.connect(
            lambda v: setattr(self.canvas, "snap_enabled", bool(v)))
        self.btn_snap_helpers.toggled.connect(
            lambda v: setattr(self.canvas, "snap_helpers", bool(v)))
        self.btn_lock_helpers.toggled.connect(
            lambda v: setattr(self.canvas, "helper_locked", bool(v)))
        self.btn_bind.toggled.connect(self._bind_mode_toggled)
        self.btn_unbind.clicked.connect(self._unbind_selected)
        self.btn_unbind_all.clicked.connect(self._unbind_all_recursive)

    def _set_tool(self, name, on):
        if on:
            for b, n in ((self.btn_tool_point, 'point'),
                         (self.btn_tool_line, 'line'),
                         (self.btn_tool_circle, 'circle')):
                if n != name and b.isChecked():
                    b.blockSignals(True);
                    b.setChecked(False);
                    b.blockSignals(False)
            self.canvas.helper_tool = name
            self.canvas.selected = []
            self.canvas.selected_helpers = []
            self.canvas.selectionChanged.emit()
            self.canvas.update()
        else:
            if self.canvas.helper_tool == name:
                self.canvas.helper_tool = None
                self.canvas.update()

    def _make_tangent(self):
        ln = None;
        cir = None
        for h in self.canvas.selected_helpers:
            if isinstance(h, HelperLine) and ln is None:
                ln = h
            elif isinstance(h, HelperCircle) and cir is None:
                cir = h
        if ln is None and self.canvas.helper_lines:
            ln = self.canvas.helper_lines[0]
        if cir is None and self.canvas.helper_circles:
            cir = self.canvas.helper_circles[0]
        if ln is None or cir is None:
            QMessageBox.information(self, _T('hint'),
                                    u"需要一个辅助线 + 一个辅助圆")
            return
        dlg = _MultiInputDialog(u"相切于圆", [
            (u"初始角度 (°)", u"0"),
            (u"控制变量", u"Time"),
            (u"每单位旋转角度 (°)", u"6"),
            (u"切线方向偏移 (°)", u"0"),
        ], self)
        if dlg.exec_() != QDialog.Accepted: return
        a0, ctrl, rate, off = dlg.values()
        if not a0: a0 = u"0"
        if not ctrl: ctrl = u"0"
        if not rate: rate = u"0"
        if not off: off = u"0"
        theta = u"(%s)+(%s)*(%s)" % (a0, ctrl, rate)  # 圆上位置角
        phi = u"(%s)-(%s)" % (theta, off)  # 切线方向角（取减，视觉逆时针）
        h2 = math.hypot(ln.dx2() - ln.dx1(), ln.dy2() - ln.dy1()) / 2.0
        h_str = _fmt(h2)
        c = cir.name or u"C1"
        # 切点 = 圆心 + R*(cos θ, sin θ)
        # 端点 = 切点 ± h2 * (sin φ, -cos φ)
        ln.expr_x1 = u"{%s_X}+{%s_R}*cos(%s)-%s*sin(%s)" % (c, c, theta, h_str, phi)
        ln.expr_y1 = u"{%s_Y}+{%s_R}*sin(%s)+%s*cos(%s)" % (c, c, theta, h_str, phi)
        ln.expr_x2 = u"{%s_X}+{%s_R}*cos(%s)+%s*sin(%s)" % (c, c, theta, h_str, phi)
        ln.expr_y2 = u"{%s_Y}+{%s_R}*sin(%s)-%s*cos(%s)" % (c, c, theta, h_str, phi)
        ln.use_expr_x1 = True;
        ln.use_expr_y1 = True
        ln.use_expr_x2 = True;
        ln.use_expr_y2 = True
        self.canvas.eval_all(0.0)
        self.canvas.update()
        self.canvas.contentChanged.emit()
        try:
            self.canvas._quick_panel.refresh()
        except Exception:
            pass

    def _make_char_attach(self):
        ln = None
        for h in self.canvas.selected_helpers:
            if isinstance(h, HelperLine): ln = h; break
        if ln is None and self.canvas.helper_lines:
            ln = self.canvas.helper_lines[0]
        if ln is None:
            QMessageBox.information(self, _T('hint'), u"需要一个辅助线")
            return
        sel = self.canvas.selected
        if not sel:
            QMessageBox.information(self, _T('hint'), _T('no_selection'))
            return
        dlg = _MultiInputDialog(u"字符吸线", [
            (u"控制量（Activate1 / Trim / PitchAngle / Time…）", u"0.5"),
            (u"控制量最小值（此时贴线起点）", u"0"),
            (u"控制量最大值（此时贴线终点）", u"1"),
            (u"允许超出线两端", False, "check"),
        ], self)
        if dlg.exec_() != QDialog.Accepted: return
        ctrl, cmin, cmax, allow_out = dlg.values()
        if not ctrl: ctrl = u"0"
        if not cmin: cmin = u"0"
        if not cmax: cmax = u"1"
        span = u"((%s)-(%s))" % (cmax, cmin)
        t_raw = u"(((%s)-(%s))/%s)" % (ctrl, cmin, span)
        t_expr = t_raw if allow_out == "1" else (u"clamp(%s,0,1)" % t_raw)
        L = ln.name or u"线1"
        dx = u"({%s_X2}-{%s_X1})" % (L, L)
        dy = u"({%s_Y2}-{%s_Y1})" % (L, L)
        pos_expr = u"({%s_X1}+%s*(%s))*20" % (L, dx, t_expr)
        vo_expr = u"-({%s_Y1}+%s*(%s))*10" % (L, dy, t_expr)
        # ★ 屏幕坐标 atan2 取负，匹配 it.rotation（正=逆时针）
        rot_expr = u"-atan2(%s,%s)" % (dy, dx)
        for it in sel:
            it.custom_pos_expr = pos_expr
            it.custom_pos_enabled = True
            it.custom_vo_expr = vo_expr
            it.custom_vo_enabled = True
            it.custom_rot_expr = rot_expr
            it.custom_rot_enabled = True
        self._updating = True
        it0 = sel[0]
        self.chk_pos_expr.setChecked(True)
        self.pos_expr_edit.setPlainText(it0.custom_pos_expr)
        self.chk_vo_expr.setChecked(True)
        self.vo_expr_edit.setPlainText(it0.custom_vo_expr)
        self.chk_rot_expr.setChecked(True)
        self.rot_expr_edit.setPlainText(it0.custom_rot_expr)
        self._updating = False
        self.canvas.eval_all(0.0)
        self.canvas.update()
        self.canvas.contentChanged.emit()
        self._update_preview()

    def _bind_mode_toggled(self, on):
        self._bind_pick_children = []
        self.canvas.bind_pick_mode = bool(on)
        try:
            self.canvas.bindPicked.disconnect(self._on_bind_picked)
        except Exception:
            pass
        if on:
            self.canvas.bindPicked.connect(self._on_bind_picked)
            self.canvas.selected = []
            self.canvas.selected_helpers = []
            self.canvas.selectionChanged.emit()
            self.canvas.update()
            try:
                mw = self.window()
                mw.statusBar().showMessage(
                    _L(u"吸附模式：点击第一个对象（作为子级）",
                       u"Bind mode: click the first object (as child)"),
                    6000)
            except Exception:
                pass

    def start_bind_with_children(self, children):
        """右键菜单调用：直接把 children 作为子级，进入拾取父级模式"""
        children = [c for c in (children or []) if c is not None]
        if not children:
            return
        # 屏蔽 toggled，避免 _bind_mode_toggled 清空我们刚设置的 children
        self.btn_bind.blockSignals(True)
        self.btn_bind.setChecked(True)
        self.btn_bind.blockSignals(False)
        try:
            self.canvas.bindPicked.disconnect(self._on_bind_picked)
        except Exception:
            pass
        self.canvas.bindPicked.connect(self._on_bind_picked)
        self._bind_pick_children = list(children)
        self.canvas.bind_pick_mode = True
        self.canvas.selected = []
        self.canvas.selected_helpers = []
        self.canvas.selectionChanged.emit()
        self.canvas.update()
        try:
            mw = self.window()
            mw.statusBar().showMessage(
                _L(u"已选中 %d 个子对象，点击另一个对象作为父级",
                   u"%d child object(s) selected, "
                   u"click another object as parent")
                % len(children), 6000)
        except Exception:
            pass

    def cancel_bind(self):
        """取消吸附模式（不产生绑定）"""
        self._bind_pick_children = []
        self.btn_bind.blockSignals(True)
        self.btn_bind.setChecked(False)
        self.btn_bind.blockSignals(False)
        self.canvas.bind_pick_mode = False
        try:
            self.canvas.bindPicked.disconnect(self._on_bind_picked)
        except Exception:
            pass
        try:
            mw = self.window()
            mw.statusBar().showMessage(
                _L(u"已取消吸附模式", u"Bind mode cancelled"), 3000)
        except Exception:
            pass

    def _on_bind_picked(self, obj):
        try:
            self._on_bind_picked_impl(obj)
        except RecursionError:
            try:
                self.btn_bind.setChecked(False)
            except Exception:
                pass
            self._bind_pick_children = []
            QMessageBox.critical(
                self, _L(u"吸附失败", u"Bind failed"),
                _L(u"绑定递归过深，已中止。\n"
                   u"请检查对象的吸附关系是否成环。",
                   u"Binding recursion too deep, aborted.\n"
                   u"Check if the binding chain has a cycle."))
        except Exception as ex:
            import traceback
            tb = traceback.format_exc()
            self._bind_pick_children = []
            try:
                self.btn_bind.setChecked(False)
            except Exception:
                pass
            QMessageBox.critical(
                self, _L(u"吸附失败", u"Bind failed"),
                u"%s\n\n%s" % (ex, tb[-1200:]))

    def _on_bind_picked_impl(self, obj):
        parent = obj
        children = list(self._bind_pick_children)
        if not children:
            # 通过工具栏按钮直接开启的情况：本次点击对象作为子级
            self._bind_pick_children = [obj]
            cn = getattr(obj, 'name', u'') or u"(无名)"
            try:
                mw = self.window()
                mw.statusBar().showMessage(
                    _L(u"已选中 [%s]，再点另一个对象作为吸附目标",
                       u"Selected [%s], click another object as target")
                    % cn, 6000)
            except Exception:
                pass
            return
        if parent in children:
            return
        # ★ 父级没名字就自动分配一个
        parent_name = getattr(parent, 'name', u'') or u""
        if not parent_name:
            try:
                if isinstance(parent, RichItem):
                    parent.name = self.canvas._next_char_name()
                elif isinstance(parent, HelperPoint):
                    parent.name = self.canvas._next_helper_name('P')
                elif isinstance(parent, HelperLine):
                    parent.name = self.canvas._next_helper_name('L')
                elif isinstance(parent, HelperCircle):
                    parent.name = self.canvas._next_helper_name('C')
            except Exception:
                pass
            parent_name = getattr(parent, 'name', u'') or u""
        # 给所有子级补名字
        for c in children:
            if isinstance(c, RichItem) and not (getattr(c, 'name', u'') or u""):
                try:
                    c.name = self.canvas._next_char_name()
                except Exception:
                    pass
        # 用第一个子级打开配置对话框
        first_child = children[0]
        dlg = BindControlDialog(first_child, parent, self.canvas, self)
        if dlg.exec_() != QDialog.Accepted:
            self.cancel_bind()
            return
        dx_expr, dy_expr, ang_expr = dlg.values()

        # 父级世界位置 / 旋转
        px, py = self.canvas._obj_pos(parent)
        parent_rot0 = self.canvas._obj_rot(parent)
        a0 = math.radians(parent_rot0)
        ca, sa = math.cos(a0), math.sin(a0)

        for child in children:
            if child is parent:
                continue
            try:
                ox, oy = self.canvas._obj_pos(child)
                wx = ox - px
                wy = oy - py
                dx = wx * ca - wy * sa
                dy = wx * sa + wy * ca
                obj_rot0 = self.canvas._obj_rot(child)
                child.bind_to = parent_name
                child.bind_dx = dx
                child.bind_dy = dy
                child.bind_angle = obj_rot0 - parent_rot0
                child.bind_dx_expr = dx_expr
                child.bind_dy_expr = dy_expr
                child.bind_angle_expr = ang_expr
                # ★ 吸附的字符自动开启偏移补偿
                if isinstance(child, RichItem):
                    child.compensate_offset = True
                # 复制对话框元信息，便于下次"修改吸附属性"恢复模式
                for attr in ('_bind_dialog_mode', '_bind_dialog_ctrl',
                             '_bind_dialog_t0', '_bind_dialog_t1',
                             '_bind_dialog_tangent',
                             '_bind_dialog_reverse',    # ★ 补上
                             '_bind_dialog_start_angle',
                             '_bind_dialog_obj_offset'):
                    if hasattr(first_child, attr):
                        try:
                            setattr(child, attr, getattr(first_child, attr))
                        except Exception:
                            pass
            except Exception:
                continue
        self.cancel_bind()
        self.canvas.eval_all(0.0)
        self.canvas.update()
        self.canvas.contentChanged.emit()

    def _unbind_selected(self):
        objs = list(self.canvas.selected) + list(self.canvas.selected_helpers)
        if not objs:
            QMessageBox.information(self, _T('hint'), _T('no_selection'))
            return
        for o in objs:
            # 把当前显示位置写回静态位置，避免跳回
            if isinstance(o, RichItem):
                if o._disp_x is not None: o.x = o._disp_x
                if o._disp_y is not None: o.y = o._disp_y
            elif isinstance(o, HelperPoint):
                if o._disp_x is not None: o.x = o._disp_x
                if o._disp_y is not None: o.y = o._disp_y
            elif isinstance(o, HelperLine):
                if o._disp_x1 is not None: o.x1 = o._disp_x1; o.y1 = o._disp_y1
                if o._disp_x2 is not None: o.x2 = o._disp_x2; o.y2 = o._disp_y2
            o.bind_to = u""
            o.bind_dx_expr = u""
            o.bind_dy_expr = u""
            o.bind_angle_expr = u""
        self.canvas.eval_all(0.0)
        self.canvas.update()
        self.canvas.contentChanged.emit()

    def _unbind_all_recursive(self):
        objs = list(self.canvas.selected) + list(self.canvas.selected_helpers)
        if not objs:
            QMessageBox.information(self, _T('hint'), _T('no_selection'))
            return
        byname = self.canvas._all_objects_by_name()
        children_map = {}
        for name, obj in byname.items():
            pn = getattr(obj, 'bind_to', u"")
            if pn:
                children_map.setdefault(pn, []).append(obj)
        related = set()
        queue = list(objs)
        while queue:
            o = queue.pop()
            if id(o) in related: continue
            related.add(id(o))
            pn = getattr(o, 'bind_to', u"")
            if pn:
                p = byname.get(pn)
                if p is not None and id(p) not in related:
                    queue.append(p)
            on = getattr(o, 'name', u"")
            if on:
                for c in children_map.get(on, []):
                    if id(c) not in related:
                        queue.append(c)
        for name, obj in byname.items():
            if id(obj) not in related: continue
            if isinstance(obj, RichItem):
                if obj._disp_x is not None: obj.x = obj._disp_x
                if obj._disp_y is not None: obj.y = obj._disp_y
            elif isinstance(obj, HelperPoint):
                if obj._disp_x is not None: obj.x = obj._disp_x
                if obj._disp_y is not None: obj.y = obj._disp_y
            elif isinstance(obj, HelperLine):
                if obj._disp_x1 is not None:
                    obj.x1 = obj._disp_x1;
                    obj.y1 = obj._disp_y1
                if obj._disp_x2 is not None:
                    obj.x2 = obj._disp_x2;
                    obj.y2 = obj._disp_y2
            obj.bind_to = u""
            obj.bind_dx_expr = u""
            obj.bind_dy_expr = u""
            obj.bind_angle_expr = u""
        self.canvas.eval_all(0.0)
        self.canvas.update()
        self.canvas.contentChanged.emit()

    def _on_text(self):
        if self._updating: return
        t = self.text_edit.text()
        sel = self.canvas.selected
        if sel:
            for it in sel:
                it.text = t
                it._display_cache = t
                it.eval_display(self.canvas.variables, 0.0)
        self.canvas.update()
        self.canvas.contentChanged.emit()
        self._update_preview()

    def _update_preview(self):
        txt = self.text_edit.text()
        if not txt: self.preview_label.setText(u"—"); return
        r = eval_text_stateful(txt, self.canvas.variables, 0.0, ExprState(), -1)
        display = re.sub(r'<[^>]+>', '', r)
        self.preview_label.setText(display)

    def _on_size(self, v):
        if self._updating: return
        r = round(float(v), 5)

        def f(it): it.size = r; it.size_is_custom = True

        self._apply(f)

    def _on_pos_expr(self):
        if self._updating: return
        t = self.pos_expr_edit.toPlainText()
        self._apply(lambda it: setattr(it, "custom_pos_expr", t))

    def _on_vo_expr(self):
        if self._updating: return
        t = self.vo_expr_edit.toPlainText()
        self._apply(lambda it: setattr(it, "custom_vo_expr", t))

    def _on_size_expr(self):
        if self._updating: return
        t = self.size_expr_edit.toPlainText()
        self._apply(lambda it: setattr(it, "custom_size_expr", t))

    def _on_rot_expr(self):
        if self._updating: return
        t = self.rot_expr_edit.toPlainText()
        self._apply(lambda it: setattr(it, "custom_rot_expr", t))

    def _on_pos_expr_toggle(self, checked):
        if self._updating: return
        self._apply(lambda it: setattr(it, "custom_pos_enabled", bool(checked)))

    def _on_vo_expr_toggle(self, checked):
        if self._updating: return
        self._apply(lambda it: setattr(it, "custom_vo_enabled", bool(checked)))

    def _on_size_expr_toggle(self, checked):
        if self._updating: return
        self._apply(lambda it: setattr(it, "custom_size_enabled", bool(checked)))

    def _on_rot_expr_toggle(self, checked):
        if self._updating: return
        self._apply(lambda it: setattr(it, "custom_rot_enabled", bool(checked)))

    def _on_color(self):
        if self._updating: return
        sel = self.canvas.selected
        if not sel: return
        c = QColorDialog.getColor(sel[0].color, self, _T('choose_color'))
        if c.isValid():
            self._apply(lambda it: setattr(it, "color", QColor(c)))
            self._set_color_btn(self.color_btn, c)

    def refresh_ranges(self):
        # 允许整数位自由输入，不随画布大小限制
        self.pos_spin.setRange(-99999.0, 99999.0)
        self.vo_spin.setRange(-99999.0, 99999.0)

    @staticmethod
    def _helper_center_pos_vo(h):
        """辅助对象的中心 → (pos, voffset) 显示值"""
        try:
            if isinstance(h, HelperPoint):
                return h.dx() * POS_PER_WORLD, -h.dy() * VO_PER_WORLD
            if isinstance(h, HelperLine):
                cx = (h.dx1() + h.dx2()) / 2.0
                cy = (h.dy1() + h.dy2()) / 2.0
                return cx * POS_PER_WORLD, -cy * VO_PER_WORLD
            if isinstance(h, HelperCircle):
                if h.point is not None:
                    return (h.point.dx() * POS_PER_WORLD,
                            -h.point.dy() * VO_PER_WORLD)
        except Exception:
            pass
        return 0.0, 0.0

    def refresh(self):
        sel = self.canvas.selected
        helpers = self.canvas.selected_helpers
        has_char = len(sel) > 0
        has_helper = len(helpers) > 0
        has_any = has_char or has_helper

        self._updating = True
        try:
            # ① 默认全禁用
            for w in self._widgets:
                w.setEnabled(False)

            # ② pos / voffset FT 栏：字符或辅助对象都启用
            if has_any:
                for w in (self.pos_spin, self.vo_spin,
                          self.chk_pos_expr, self.pos_expr_edit,
                          self.chk_vo_expr, self.vo_expr_edit):
                    w.setEnabled(True)

            if has_char:
                # ③ 选中字符 → 全部启用（沿用原逻辑）
                for w in self._widgets:
                    w.setEnabled(True)
                it = sel[0]
                self.text_edit.setText(it.text)
                self.size_spin.setValue(it.size)
                self.rot_spin.setValue(it.rotation)
                self.bold_btn.setChecked(it.bold)
                self.italic_btn.setChecked(it.italic)
                self.underline_btn.setChecked(it.underline)
                self.strike_btn.setChecked(it.strike)
                self._set_color_btn(self.color_btn, it.color)
                self.pos_spin.setValue(it.x * POS_PER_WORLD)
                self.vo_spin.setValue(-it.y * VO_PER_WORLD)
                self.chk_pos_expr.setChecked(it.custom_pos_enabled)
                self.pos_expr_edit.setPlainText(it.custom_pos_expr)
                self.chk_vo_expr.setChecked(it.custom_vo_enabled)
                self.vo_expr_edit.setPlainText(it.custom_vo_expr)
                self.chk_size_expr.setChecked(it.custom_size_enabled)
                self.size_expr_edit.setPlainText(it.custom_size_expr)
                self.chk_rot_expr.setChecked(it.custom_rot_enabled)
                self.rot_expr_edit.setPlainText(it.custom_rot_expr)
            elif has_helper:
                # ④ 选中辅助对象 → 只填 pos / voffset 相关栏
                h = helpers[0]
                self.text_edit.setText(u"")
                pos_val, vo_val = self._helper_center_pos_vo(h)
                self.pos_spin.setValue(pos_val)
                self.vo_spin.setValue(vo_val)
                self.chk_pos_expr.setChecked(
                    getattr(h, 'custom_pos_enabled', False))
                self.pos_expr_edit.setPlainText(
                    getattr(h, 'custom_pos_expr', u""))
                self.chk_vo_expr.setChecked(
                    getattr(h, 'custom_vo_enabled', False))
                self.vo_expr_edit.setPlainText(
                    getattr(h, 'custom_vo_expr', u""))
        finally:
            self._updating = False
        self._update_preview()

    def update_geometry(self):
        sel = self.canvas.selected
        helpers = self.canvas.selected_helpers
        self._updating = True
        try:
            if sel:
                it = sel[0]
                self.pos_spin.setValue(it.x * POS_PER_WORLD)
                self.vo_spin.setValue(-it.y * VO_PER_WORLD)
                self.rot_spin.setValue(it.rotation)
                self.size_spin.setValue(it.size)
            elif helpers:
                pos_val, vo_val = self._helper_center_pos_vo(helpers[0])
                self.pos_spin.setValue(pos_val)
                self.vo_spin.setValue(vo_val)
        finally:
            self._updating = False

    def focus_text(self):
        self.text_edit.setFocus();
        self.text_edit.selectAll()

    def refresh_preview(self):
        self._update_preview()


# ==================================================== 树形字符选择表
ROLE_ITEM = Qt.UserRole + 1
ROLE_FOLDER = Qt.UserRole + 2
ROLE_SIDE = Qt.UserRole + 3
ROLE_HELPER = Qt.UserRole + 10


def _make_color_icon(color, sz=12):
    pm = QPixmap(sz, sz)
    pm.fill(color)
    return QIcon(pm)


class CharTreeWidget(QTreeWidget):
    dropped = pyqtSignal()
    deleteRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDropIndicatorShown(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def keyPressEvent(self, e):
        # ★ Del 键 → 请求删除选中项
        if e.key() == Qt.Key_Delete:
            self.deleteRequested.emit()
            return
        super().keyPressEvent(e)

    def _from_other_tree(self, e):
        src = e.source()
        return (src is not None) and (src is not self) and isinstance(src, CharTreeWidget)

    def dragEnterEvent(self, e):
        if self._from_other_tree(e):
            e.acceptProposedAction();
            return
        super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if self._from_other_tree(e):
            e.acceptProposedAction();
            return
        super().dragMoveEvent(e)

    def dropEvent(self, e):
        if not self._from_other_tree(e):
            super().dropEvent(e);
            self.dropped.emit();
            return
        src = e.source()
        src_items = list(src.selectedItems())
        if not src_items:
            e.ignore();
            return
        target_item = self.itemAt(e.pos())
        for it in src_items:
            p = it.parent()
            if p is None:
                idx = src.indexOfTopLevelItem(it)
                if idx >= 0: src.takeTopLevelItem(idx)
            else:
                p.removeChild(it)
            if target_item is None:
                self.addTopLevelItem(it)
            elif target_item.data(0, ROLE_FOLDER) is not None:
                target_item.addChild(it);
                target_item.setExpanded(True)
            else:
                p2 = target_item.parent()
                if p2 is None:
                    idx2 = self.indexOfTopLevelItem(target_item)
                    self.insertTopLevelItem(idx2 + 1, it)
                else:
                    idx2 = p2.indexOfChild(target_item)
                    p2.insertChild(idx2 + 1, it)
        e.acceptProposedAction();
        self.dropped.emit()


class CharListPanel(QWidget):
    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self.canvas = canvas;
        self._updating = False
        self._dual_mode = False
        self.setMinimumHeight(120)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6);
        lay.setSpacing(4)
        self.title_label = QLabel(_T('char_table'))
        lay.addWidget(self.title_label)

        row1 = QHBoxLayout();
        row1.setSpacing(4);
        row1.setContentsMargins(0, 0, 0, 0)
        self.btn_new_folder = QPushButton(_T('new_folder'))
        self.btn_rename = QPushButton(_T('rename'))
        self.btn_delete = QPushButton(_T('del'))
        for b in (self.btn_new_folder, self.btn_rename, self.btn_delete):
            b.setFixedHeight(24);
            fb = b.font();
            fb.setPointSize(9);
            b.setFont(fb)
            row1.addWidget(b, 1)
        lay.addLayout(row1)

        row2 = QHBoxLayout();
        row2.setSpacing(4);
        row2.setContentsMargins(0, 0, 0, 0)
        self.btn_dual = QPushButton(_T('dual'));
        self.btn_dual.setCheckable(True)
        self.btn_vis = QPushButton(_T('hide_show'))
        self.btn_up = QPushButton(_T('move_up'))
        self.btn_down = QPushButton(_T('move_down'))
        self.btn_share = QPushButton(_T('share'))
        self.btn_import = QPushButton(_T('import'))
        for b in (self.btn_dual, self.btn_vis, self.btn_up, self.btn_down,
                  self.btn_share, self.btn_import):
            b.setFixedHeight(24);
            fb = b.font();
            fb.setPointSize(9);
            b.setFont(fb)
            row2.addWidget(b, 1)
        lay.addLayout(row2)

        self.tree_stack = QWidget()
        st_lay = QHBoxLayout(self.tree_stack)
        st_lay.setContentsMargins(0, 0, 0, 0);
        st_lay.setSpacing(2)
        self.tree = CharTreeWidget();
        self.tree_left = CharTreeWidget()
        self.tree_right = CharTreeWidget()
        for t in (self.tree, self.tree_left, self.tree_right):
            t.setHeaderHidden(True)
            t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        st_lay.addWidget(self.tree, 1);
        st_lay.addWidget(self.tree_left, 1)
        st_lay.addWidget(self.tree_right, 1)
        self.tree_left.hide();
        self.tree_right.hide()
        lay.addWidget(self.tree_stack)
        for t in (self.tree, self.tree_left, self.tree_right):
            t.itemSelectionChanged.connect(self._on_tree_selection)
            t.itemDoubleClicked.connect(self._on_double_click)
            t.dropped.connect(self._on_dropped)
            t.deleteRequested.connect(self._delete_selected)
            t.setContextMenuPolicy(Qt.CustomContextMenu)
            t.customContextMenuRequested.connect(
                lambda pos, tree=t: self._on_tree_context_menu(tree, pos))
        self.btn_new_folder.clicked.connect(self._create_folder)
        self.btn_rename.clicked.connect(self._rename_selected)
        self.btn_delete.clicked.connect(self._delete_selected)
        self.btn_vis.clicked.connect(self._toggle_visibility)
        self.btn_up.clicked.connect(lambda: self._move_selected(-1))
        self.btn_down.clicked.connect(lambda: self._move_selected(+1))
        self.btn_share.clicked.connect(self._share)
        self.btn_import.clicked.connect(self._import)
        self.btn_dual.toggled.connect(self._on_dual_toggle)
        self.canvas.itemsChanged.connect(self.rebuild)
        self.canvas.selectionChanged.connect(self.sync_selection)
        self.canvas.contentChanged.connect(self.refresh_texts)
        self.rebuild()

    def _on_dual_toggle(self, on):
        self._dual_mode = bool(on)
        self.btn_dual.setText(_T('single') if on else _T('dual'))
        self.tree.setVisible(not on)
        self.tree_left.setVisible(on)
        self.tree_right.setVisible(on)
        self.rebuild()
        # ★ 切换单双排后，默认把所有文件夹收起
        self._collapse_all_folders()

    def _collapse_all_folders(self):
        """递归把所有文件夹节点都设为收起状态。"""
        def walk(qi):
            if qi.data(0, ROLE_FOLDER) is not None:
                qi.setExpanded(False)
            for i in range(qi.childCount()):
                walk(qi.child(i))
        for t in (self.tree, self.tree_left, self.tree_right):
            for i in range(t.topLevelItemCount()):
                walk(t.topLevelItem(i))

    def _collect_collapsed(self, tree):
        collapsed = set()

        def walk(qi, path):
            fname = qi.data(0, ROLE_FOLDER)
            if fname is None: return
            new_path = path + (fname,)
            if not qi.isExpanded(): collapsed.add(new_path)
            for i in range(qi.childCount()): walk(qi.child(i), new_path)

        for i in range(tree.topLevelItemCount()): walk(tree.topLevelItem(i), ())
        return collapsed

    def _restore_collapsed(self, tree, collapsed):
        def walk(qi, path):
            fname = qi.data(0, ROLE_FOLDER)
            if fname is None: return
            new_path = path + (fname,)
            if new_path in collapsed:
                qi.setExpanded(False)
            else:
                qi.setExpanded(True)
            for i in range(qi.childCount()): walk(qi.child(i), new_path)

        for i in range(tree.topLevelItemCount()): walk(tree.topLevelItem(i), ())

    def rebuild(self):
        cs = self._collect_collapsed(self.tree)
        cl = self._collect_collapsed(self.tree_left)
        cr = self._collect_collapsed(self.tree_right)
        self._updating = True
        for t in (self.tree, self.tree_left, self.tree_right): t.clear()

        def build_children(node, parent_qi):
            for c in node.children:
                if c.folder:
                    qi = QTreeWidgetItem(parent_qi)
                    qi.setText(0, u"📁 " + (c.name or u"文件夹"))
                    qi.setData(0, ROLE_FOLDER, c.name or u"文件夹")
                    qi.setFlags(qi.flags() | Qt.ItemIsDragEnabled
                                | Qt.ItemIsDropEnabled | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    build_children(c, qi)
                elif getattr(c, 'helper', None) is not None:
                    qi = QTreeWidgetItem(parent_qi)
                    h = c.helper
                    kind = (u"● 点" if isinstance(h, HelperPoint)
                            else u"／ 线" if isinstance(h, HelperLine)
                    else u"○ 圆")
                    vis = u"" if getattr(h, 'visible', True) else u"🚫 "
                    qi.setText(0, u"%s%s %s" % (vis, kind, h.name or u"(未命名)"))
                    qi.setData(0, ROLE_HELPER, h)
                    qi.setFlags((qi.flags() | Qt.ItemIsDragEnabled
                                 | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                                & ~Qt.ItemIsDropEnabled)
                else:
                    qi = QTreeWidgetItem(parent_qi)
                    it = c.item
                    try:
                        prefix = u"🚫 " if it.hidden else u""
                        qi.setText(0, u"%s%s   %s   %s"
                                   % (prefix, it.text, _fmt(it.size),
                                      it.color.name().upper()))
                        qi.setIcon(0, _make_color_icon(it.color, 12))
                        if it.hidden:
                            qi.setForeground(0, QBrush(QColor("#999999")))
                    except Exception:
                        qi.setText(0, u"%s" % it.text)
                    qi.setData(0, ROLE_ITEM, it)
                    qi.setFlags((qi.flags() | Qt.ItemIsDragEnabled
                                 | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                                & ~Qt.ItemIsDropEnabled)

        if not self._dual_mode:
            build_children(self.canvas.root, self.tree.invisibleRootItem())
            self._restore_collapsed(self.tree, cs)
        else:
            left_list = [];
            right_list = []
            for c in self.canvas.root.children:
                if c.dual_side == 'R':
                    right_list.append(c)
                elif c.dual_side == 'L':
                    left_list.append(c)
                else:
                    if len(left_list) <= len(right_list):
                        c.dual_side = 'L';
                        left_list.append(c)
                    else:
                        c.dual_side = 'R';
                        right_list.append(c)

            class _H:
                def __init__(self, ch): self.children = ch

            build_children(_H(left_list), self.tree_left.invisibleRootItem())
            build_children(_H(right_list), self.tree_right.invisibleRootItem())
            self._restore_collapsed(self.tree_left, cl)
            self._restore_collapsed(self.tree_right, cr)
        self._updating = False
        self.sync_selection()

    def refresh_texts(self):
        def walk(qi):
            it = qi.data(0, ROLE_ITEM)
            if it is not None:
                try:
                    prefix = u"🚫 " if it.hidden else u""
                    qi.setText(0, u"%s%s   %s   %s"
                               % (prefix, it.text, _fmt(it.size),
                                  it.color.name().upper()))
                    qi.setIcon(0, _make_color_icon(it.color, 12))
                    if it.hidden:
                        qi.setForeground(0, QBrush(QColor("#999999")))
                    else:
                        qi.setForeground(0, QBrush(QColor("#000000")))
                except Exception:
                    qi.setText(0, u"%s" % it.text)
            for i in range(qi.childCount()): walk(qi.child(i))

        for t in (self.tree, self.tree_left, self.tree_right):
            for i in range(t.topLevelItemCount()): walk(t.topLevelItem(i))

    def sync_selection(self):
        if self._updating: return
        self._updating = True
        sids = set(id(it) for it in self.canvas.selected)

        def walk(qi):
            data = qi.data(0, ROLE_ITEM)
            if data is not None:
                qi.setSelected(id(data) in sids)
            else:
                qi.setSelected(False)
            for i in range(qi.childCount()): walk(qi.child(i))

        for t in (self.tree, self.tree_left, self.tree_right):
            for i in range(t.topLevelItemCount()): walk(t.topLevelItem(i))
        self._updating = False

    def _on_tree_selection(self):
        if self._updating: return
        selected = [];
        selected_helpers = []

        def walk(qi):
            data = qi.data(0, ROLE_ITEM)
            helper = qi.data(0, ROLE_HELPER)
            if data is not None and qi.isSelected(): selected.append(data)
            if helper is not None and qi.isSelected(): selected_helpers.append(helper)
            for i in range(qi.childCount()): walk(qi.child(i))

        for t in (self.tree, self.tree_left, self.tree_right):
            for i in range(t.topLevelItemCount()): walk(t.topLevelItem(i))
        self.canvas.selected = selected
        self.canvas.selected_helpers = selected_helpers
        self._updating = True
        self.canvas.selectionChanged.emit();
        self.canvas.update()
        self._updating = False

    def _on_tree_context_menu(self, tree, pos):
        """字符树右键菜单：重命名 / 隐藏 / 删除"""
        item = tree.itemAt(pos)
        if item is None:
            return
        # 若右键点中的项未选中 → 改为只选它
        if not item.isSelected():
            self._updating = True
            tree.clearSelection()
            item.setSelected(True)
            tree.setCurrentItem(item)
            self._updating = False
            self._on_tree_selection()
        m = QMenu(self)
        act_rename = m.addAction(_T('rename'))
        act_rename.triggered.connect(self._rename_selected)
        act_hide = m.addAction(_T('hide_show'))
        act_hide.triggered.connect(self._toggle_visibility)
        act_del = m.addAction(_T('del'))
        act_del.triggered.connect(self._delete_selected)
        m.exec_(tree.viewport().mapToGlobal(pos))

    def _on_double_click(self, qi, col):
        data = qi.data(0, ROLE_ITEM)
        helper = qi.data(0, ROLE_HELPER)
        if data is not None:
            self.canvas.selected = [data]
            self.canvas.selected_helpers = []
            self._updating = True
            self.canvas.selectionChanged.emit()
            self.canvas.update()
            self._updating = False
            return
        if helper is not None:
            old = getattr(helper, 'name', u"") or u""
            new, ok = self._ask_text(
                _L(u"重命名辅助对象", u"Rename Helper"),
                _L(u"新名称：", u"New name:"),
                old)
            if not ok: return
            new = new.strip()
            if not new or new == old: return
            helper.name = new
            self.canvas.contentChanged.emit()
            self.rebuild()

    def _tree_to_canvas(self):
        new_root = Node(folder=True)

        def build_into(qi, parent_node, top_side=None):
            for i in range(qi.childCount()):
                c = qi.child(i)
                item = c.data(0, ROLE_ITEM)
                helper = c.data(0, ROLE_HELPER)
                fname = c.data(0, ROLE_FOLDER)
                if item is not None:
                    node = Node(folder=False, item=item, parent=parent_node)
                    node.dual_side = top_side
                    parent_node.children.append(node)
                elif helper is not None:
                    node = Node(folder=False, helper=helper, parent=parent_node)
                    node.dual_side = top_side
                    parent_node.children.append(node)
                else:
                    node = Node(folder=True, name=fname or u"文件夹", parent=parent_node)
                    node.dual_side = top_side
                    parent_node.children.append(node)
                    build_into(c, node, None)

        if not self._dual_mode:
            build_into(self.tree.invisibleRootItem(), new_root, None)
        else:
            build_into(self.tree_left.invisibleRootItem(), new_root, 'L')
            build_into(self.tree_right.invisibleRootItem(), new_root, 'R')
        self.canvas.root = new_root
        self.canvas._resync_helper_lists()

    def _on_dropped(self):
        self._tree_to_canvas()
        self.canvas.eval_all(0.0);
        self.canvas.update()
        self.canvas.contentChanged.emit();
        self.refresh_texts()

    def _selected_tree_items(self):
        out = []

        def walk(qi):
            if qi.isSelected(): out.append(qi)
            for i in range(qi.childCount()): walk(qi.child(i))

        for t in (self.tree, self.tree_left, self.tree_right):
            for i in range(t.topLevelItemCount()): walk(t.topLevelItem(i))
        return out

    def _ask_text(self, title, label, default=u""):
        """弹一个文本框输入对话框，并彻底去掉右上角的 ? 按钮。"""
        dlg = QInputDialog(self)
        dlg.setWindowTitle(title)
        dlg.setLabelText(label)
        dlg.setTextValue(default)
        dlg.setInputMode(QInputDialog.TextInput)
        # ★ 真正去掉问号（用实例 setWindowFlags，而不是静态 getText 的 flags 参数）
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        if dlg.exec_() == QDialog.Accepted:
            return dlg.textValue(), True
        return u"", False

    def _create_folder(self):
        name, ok = self._ask_text(
            _L(u"新建文件夹", u"New Folder"),
            _L(u"名称：", u"Name:"),
            _L(u"新文件夹", u"New Folder"))
        if not ok:
            return
        default_name = _L(u"文件夹", u"Folder")
        cs = self._collect_collapsed(self.tree)
        cl = self._collect_collapsed(self.tree_left)
        cr = self._collect_collapsed(self.tree_right)
        qi = QTreeWidgetItem()
        qi.setText(0, u"📁 " + (name or default_name))
        qi.setData(0, ROLE_FOLDER, name or default_name)
        qi.setFlags(qi.flags() | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled
                    | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        target_tree = self.tree_right if self._dual_mode else self.tree
        sel = self._selected_tree_items()
        if sel:
            target = sel[0]
            parent = target.parent()
            if parent is None:
                target_tree.addTopLevelItem(qi)
            else:
                parent.addChild(qi)
        else:
            target_tree.addTopLevelItem(qi)
        target_tree.setCurrentItem(qi)
        qi.setExpanded(True)
        self._restore_collapsed(self.tree, cs)
        self._restore_collapsed(self.tree_left, cl)
        self._restore_collapsed(self.tree_right, cr)
        self._tree_to_canvas()
        self.canvas.update()
        self.canvas.itemsChanged.emit()
        self.canvas.contentChanged.emit()

    def _rename_selected(self):
        sel = self._selected_tree_items()
        if not sel:
            return
        qi = sel[0]
        helper = qi.data(0, ROLE_HELPER)
        # 辅助对象重命名
        if helper is not None:
            old = getattr(helper, 'name', u"") or u""
            new, ok = self._ask_text(
                _L(u"重命名辅助对象", u"Rename Helper"),
                _L(u"新名称：", u"New name:"),
                old)
            if not ok:
                return
            new = new.strip()
            if not new or new == old:
                return
            helper.name = new
            self.canvas.contentChanged.emit()
            self.rebuild()
            return
        # 文件夹重命名
        fname = qi.data(0, ROLE_FOLDER)
        if fname is None:
            QMessageBox.information(
                self, _T('hint'),
                _L(u"只能重命名文件夹或辅助对象。",
                   u"Only folders or helpers can be renamed."))
            return
        name, ok = self._ask_text(
            _L(u"重命名文件夹", u"Rename Folder"),
            _L(u"名称：", u"Name:"),
            fname)
        if not ok:
            return
        qi.setText(0, u"📁 " + (name or _L(u"文件夹", u"Folder")))
        qi.setData(0, ROLE_FOLDER, name or _L(u"文件夹", u"Folder"))
        self._tree_to_canvas()
        self.canvas.itemsChanged.emit()
        self.canvas.contentChanged.emit()

    def _delete_selected(self):
        sel = self._selected_tree_items()
        if not sel: return
        removed = []

        def collect(qi):
            item = qi.data(0, ROLE_ITEM)
            if item is not None: removed.append(item)
            for i in range(qi.childCount()): collect(qi.child(i))

        for qi in sel:
            collect(qi)
            parent = qi.parent()
            if parent is None:
                for t in (self.tree, self.tree_left, self.tree_right):
                    idx = t.indexOfTopLevelItem(qi)
                    if idx >= 0: t.takeTopLevelItem(idx); break
            else:
                parent.removeChild(qi)
        self.canvas.selected = [x for x in self.canvas.selected if x not in removed]
        self._tree_to_canvas();
        self.canvas.update()
        self.canvas.selectionChanged.emit();
        self.canvas.itemsChanged.emit()
        self.canvas.contentChanged.emit()

    def _collect_items_in_treesel(self):
        out = [];
        helpers = []

        def walk(qi):
            it = qi.data(0, ROLE_ITEM)
            h = qi.data(0, ROLE_HELPER)
            if it is not None: out.append(it)
            if h is not None: helpers.append(h)
            for i in range(qi.childCount()): walk(qi.child(i))

        for qi in self._selected_tree_items(): walk(qi)
        return out, helpers

    def _toggle_visibility(self):
        items, helpers = self._collect_items_in_treesel()
        if not items and not helpers:
            items = list(self.canvas.selected)
            helpers = list(self.canvas.selected_helpers)
            if not items and not helpers:
                QMessageBox.information(self, _T('hint'), _T('no_selection'));
                return
        all_hidden = all(getattr(x, 'hidden', not getattr(x, 'visible', True))
                         for x in items + helpers)
        new_state = not all_hidden
        for it in items: it.hidden = new_state
        for h in helpers: h.visible = not new_state  # 反向：显示=可见
        self.canvas.update();
        self.canvas.contentChanged.emit()
        self.rebuild()

    def _move_selected(self, direction):
        sel = self._selected_tree_items()
        if not sel: return
        for qi in sel:
            parent = qi.parent()
            if parent is None:
                for t in (self.tree, self.tree_left, self.tree_right):
                    idx = t.indexOfTopLevelItem(qi)
                    if idx >= 0:
                        ni = idx + direction
                        if 0 <= ni < t.topLevelItemCount():
                            item = t.takeTopLevelItem(idx)
                            t.insertTopLevelItem(ni, item)
                        break
            else:
                idx = parent.indexOfChild(qi);
                ni = idx + direction
                if 0 <= ni < parent.childCount():
                    child = parent.takeChild(idx);
                    parent.insertChild(ni, child)
        self._updating = True
        for qi in sel: qi.setSelected(True)
        self._updating = False
        self._tree_to_canvas();
        self.canvas.update();
        self.canvas.contentChanged.emit()

    def _node_to_dict(self, node, hidx=None):
        if node.folder:
            return {"type": "folder", "name": node.name,
                    "children": [self._node_to_dict(c, hidx)
                                 for c in node.children]}
        h = getattr(node, 'helper', None)
        if h is not None:
            idx = hidx.get(id(h), -1) if hidx else -1
            return {"type": "helper_ref", "index": idx}
        return {"type": "item", "item": node.item.to_dict()}

    def _share(self):
        pts = self.canvas.helper_points
        lns = self.canvas.helper_lines
        cirs = self.canvas.helper_circles
        hlist = pts + lns + cirs
        hidx = {id(h): i for i, h in enumerate(hlist)}
        data = {"version": 2,
                "helpers": _encode_helpers(pts, lns, cirs),
                "root": self._node_to_dict(self.canvas.root, hidx)}
        text = json.dumps(data, ensure_ascii=False, indent=2)
        dlg = QDialog(self);
        dlg.setWindowTitle(_T('share_title'));
        dlg.resize(520, 440)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel(_T('share_hint')))
        edit = QPlainTextEdit();
        edit.setPlainText(text);
        edit.setReadOnly(True)
        f = QFont("Consolas");
        f.setPointSize(9);
        edit.setFont(f)
        v.addWidget(edit)
        row = QHBoxLayout()
        bc = QPushButton(_T('copy_clip'));
        bcl = QPushButton(_T('close'))
        row.addStretch(1);
        row.addWidget(bc);
        row.addWidget(bcl);
        v.addLayout(row)

        def do_copy():
            QGuiApplication.clipboard().setText(text);
            bc.setText(_T('copied'))

        bc.clicked.connect(do_copy);
        bcl.clicked.connect(dlg.accept);
        dlg.exec_()

    def _dict_to_node(self, d, hlist=None):
        if d.get("type") == "folder":
            n = Node(folder=True, name=d.get("name", u"文件夹"))
            for c in d.get("children", []):
                ch = self._dict_to_node(c, hlist)
                ch.parent = n;
                n.children.append(ch)
            return n
        if d.get("type") == "helper_ref":
            idx = int(d.get("index", -1))
            h = hlist[idx] if hlist and 0 <= idx < len(hlist) else None
            return Node(folder=False, helper=h)
        return Node(folder=False, item=RichItem.from_dict(d.get("item", {})))

    def _import(self):
        dlg = QDialog(self);
        dlg.setWindowTitle(_T('import_title'));
        dlg.resize(520, 440)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel(_T('import_hint')))
        edit = QPlainTextEdit();
        f = QFont("Consolas");
        f.setPointSize(9)
        edit.setFont(f);
        v.addWidget(edit)
        row = QHBoxLayout()
        ok = QPushButton(_T('import_ok'));
        cc = QPushButton(_T('cancel'))
        row.addStretch(1);
        row.addWidget(ok);
        row.addWidget(cc);
        v.addLayout(row)

        def do_import():
            text = edit.toPlainText().strip()
            if not text:
                QMessageBox.information(dlg, _T('hint'), _T('empty_content'));
                return
            try:
                data = json.loads(text)
            except Exception as ex:
                QMessageBox.warning(dlg, _T('fail'), _T('json_fail') + str(ex));
                return
            rd = data.get("root")
            if not rd:
                QMessageBox.warning(dlg, _T('fail'), _T('no_root'));
                return
            pts, lns, cirs = _decode_helpers(data.get("helpers", []))
            hlist = pts + lns + cirs
            nr = self._dict_to_node(rd, hlist)
            nr.parent = None;
            nr.folder = True
            self.canvas.root = nr
            self.canvas._resync_helper_lists()
            # 序号同步
            try:
                mw = self.window()
                if hasattr(mw, '_sync_helper_name_seq'):
                    mw._sync_helper_name_seq()
            except Exception:
                pass
            self.canvas.selected = []
            self.canvas.selected_helpers = []
            self.canvas.selectionChanged.emit();
            self.canvas.update()
            self.canvas.itemsChanged.emit();
            self.canvas.contentChanged.emit()
            dlg.accept();
            self.rebuild()

        ok.clicked.connect(do_import);
        cc.clicked.connect(dlg.accept);
        dlg.exec_()


# ==================================================== 基础控件
class ActivateButton(QPushButton):
    def __init__(self, name, default_on=False, parent=None):
        super().__init__(name, parent)
        self.setCheckable(True);
        self.setChecked(default_on)
        self.setFixedHeight(24);
        self.setMinimumWidth(76)
        f = self.font();
        f.setPointSize(8);
        self.setFont(f)

    def value(self): return 1 if self.isChecked() else -1


class SquareButton(QPushButton):
    def __init__(self, name, short, default_on=False,
                 on_value=1, off_value=0, parent=None):
        super().__init__(short, parent)
        self.setCheckable(True);
        self.setChecked(default_on)
        self.setFixedHeight(28);
        self.setMinimumWidth(88)
        self.setToolTip(name)
        f = self.font();
        f.setPointSize(8);
        f.setBold(True);
        self.setFont(f)
        self._on = on_value;
        self._off = off_value

    def value(self): return self._on if self.isChecked() else self._off


class _VSlider(QSlider):
    def __init__(self, parent=None): super().__init__(Qt.Vertical, parent)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape and self._rotate_obj is not None:
            self._exit_rotate_mode()
            return
        super().keyPressEvent(e)

    def wheelEvent(self, e):
        d = e.angleDelta().y()
        if d == 0: e.ignore(); return
        self.setValue(self.value() + (100 if d > 0 else -100));
        e.accept()


class VerticalSlider(QWidget):
    SNAP_PCT = 200  # 0.02 单位（10000 单位 = 1.0 → 200 = 0.02）

    def __init__(self, name, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self);
        lay.setContentsMargins(2, 2, 2, 2);
        lay.setSpacing(4)
        label = QLabel(name);
        label.setAlignment(Qt.AlignCenter)
        f = label.font();
        f.setBold(True);
        label.setFont(f);
        lay.addWidget(label)
        self.slider = _VSlider(self)
        self.slider.setRange(-10000, 10000);
        self.slider.setValue(0)
        self.slider.setSingleStep(100);
        self.slider.setPageStep(100)
        self.slider.setTickPosition(QSlider.TicksBothSides);
        self.slider.setTickInterval(2000)
        self.slider.setFixedWidth(26);
        self.slider.setMinimumHeight(60)
        lay.addWidget(self.slider, 1, Qt.AlignHCenter)
        br = QHBoxLayout();
        br.setContentsMargins(0, 0, 0, 0);
        br.setSpacing(2)
        self.value_spin = VTOLTrimSpin()
        self.value_spin.setAlignment(Qt.AlignCenter);
        self.value_spin.setFixedWidth(70)
        br.addWidget(self.value_spin)
        self.btn_reset = QPushButton(u"↺");
        self.btn_reset.setFixedSize(20, 20)
        fb = self.btn_reset.font();
        fb.setPointSize(9);
        self.btn_reset.setFont(fb)
        br.addWidget(self.btn_reset);
        lay.addLayout(br)
        self.slider.valueChanged.connect(self._on_slider_changed)
        self.value_spin.valueChanged.connect(self._on_spin_changed)
        self.btn_reset.clicked.connect(self._on_reset)

    def wheelEvent(self, e):
        d = e.angleDelta().y()
        if d == 0: e.ignore(); return
        self.set_value(self.value() + (0.01 if d > 0 else -0.01));
        e.accept()

    def _on_slider_changed(self, v):
        if v != 0 and abs(v) <= self.SNAP_PCT:
            self.slider.blockSignals(True);
            self.slider.setValue(0)
            self.slider.blockSignals(False);
            v = 0
        self.value_spin.blockSignals(True)
        self.value_spin.setValue(v / 10000.0)
        self.value_spin.blockSignals(False)

    def _on_spin_changed(self, val):
        v = max(-10000, min(10000, int(round(float(val) * 10000))))
        self.slider.blockSignals(True)
        self.slider.setValue(v)
        self.slider.blockSignals(False)
        # ★ 手动 emit：让主窗口的 _on_controls_changed 收到通知，
        #   立即刷新吸附到线/圆上的元素位置
        #   （否则手动输入 VTOL / Trim 数值后画面不刷新）
        self.slider.valueChanged.emit(self.slider.value())

    def _on_reset(self):
        self.set_value(0.0)

    def value(self):
        return self.slider.value() / 10000.0

    def set_value(self, v):
        self.slider.setValue(int(round(float(v) * 10000)))


class _HeadingDial(QWidget):
    valueChanged = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0.0;
        self._dragging = False
        self._start_angle = 0.0;
        self._start_value = 0.0
        self.setFixedSize(52, 52);
        self.setCursor(Qt.CrossCursor)

    def value(self):
        return self._value

    def set_value(self, v):
        v = float(v);
        v = ((v + 180.0) % 360.0) - 180.0
        if v <= -180.0 + 1e-9: v = 180.0
        self._value = v;
        self.update();
        self.valueChanged.emit(v)

    def paintEvent(self, e):
        p = QPainter(self);
        p.setRenderHint(QPainter.Antialiasing, True)
        cx = self.width() / 2.0;
        cy = self.height() / 2.0
        r = min(cx, cy) - 3
        p.setPen(QPen(QColor("#888"), 2));
        p.setBrush(QBrush(QColor("#3a3a3a")))
        p.drawEllipse(QPointF(cx, cy), r, r)
        p.setPen(QPen(QColor("#aaa"), 1))
        for ang in range(-180, 181, 45):
            rad = math.radians(ang - 90)
            p.drawLine(QPointF(cx + math.cos(rad) * (r - 2), cy + math.sin(rad) * (r - 2)),
                       QPointF(cx + math.cos(rad) * (r - 7), cy + math.sin(rad) * (r - 7)))
        rad = math.radians(self._value - 90)
        p.setPen(QPen(QColor("#00a0ff"), 3))
        p.drawLine(QPointF(cx + math.cos(rad) * (r - 13), cy + math.sin(rad) * (r - 13)),
                   QPointF(cx + math.cos(rad) * (r - 3), cy + math.sin(rad) * (r - 3)))
        p.setBrush(QBrush(QColor("#00a0ff")));
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), 3, 3)

    def wheelEvent(self, e):
        d = e.angleDelta().y()
        if d == 0: e.ignore(); return
        self.set_value(self._value + (1.0 if d > 0 else -1.0));
        e.accept()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._dragging = True
            cx = self.width() / 2.0;
            cy = self.height() / 2.0
            self._start_angle = math.atan2(e.pos().y() - cy, e.pos().x() - cx)
            self._start_value = self._value
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        if self._dragging:
            cx = self.width() / 2.0;
            cy = self.height() / 2.0
            cur = math.atan2(e.pos().y() - cy, e.pos().x() - cx)
            d = math.degrees(cur - self._start_angle)
            if d > 180:
                d -= 360
            elif d < -180:
                d += 360
            self.set_value(self._start_value + d)

    def mouseReleaseEvent(self, e):
        self._dragging = False;
        self.setCursor(Qt.CrossCursor)


class HeadingKnob(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2);
        lay.setSpacing(8)
        title = QLabel(u"Heading")
        f = title.font();
        f.setBold(True);
        title.setFont(f)
        title.setFixedWidth(60);
        lay.addWidget(title)
        self.dial = _HeadingDial(self);
        lay.addWidget(self.dial)
        self.spin = QDoubleSpinBox()
        self.spin.setRange(-180.0, 180.0);
        self.spin.setDecimals(4)
        self.spin.setKeyboardTracking(False)
        self.spin.setSingleStep(1.0);
        self.spin.setValue(0.0)
        self.spin.setAlignment(Qt.AlignCenter);
        self.spin.setFixedWidth(90)
        self.spin.setSuffix(u" °");
        lay.addWidget(self.spin)
        self.btn_reset = QPushButton(u"↺");
        self.btn_reset.setFixedSize(22, 22)
        lay.addWidget(self.btn_reset)
        self.dial.valueChanged.connect(self._on_dial_changed)
        self.spin.valueChanged.connect(self._on_spin_changed)
        self.btn_reset.clicked.connect(self._on_reset)

    def _on_dial_changed(self, v):
        self.spin.blockSignals(True);
        self.spin.setValue(v);
        self.spin.blockSignals(False)

    def _on_spin_changed(self, v): self.dial.set_value(v)

    def _on_reset(self):
        self.dial.set_value(0.0);
        self.spin.blockSignals(True)
        self.spin.setValue(0.0);
        self.spin.blockSignals(False)

    def value(self): return self.dial.value()


class AoAKnob(QWidget):
    valueChanged = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2);
        lay.setSpacing(8)
        title = QLabel(u"AoA")
        f = title.font();
        f.setBold(True);
        title.setFont(f)
        title.setFixedWidth(50);
        lay.addWidget(title)
        self.dial = _HeadingDial(self)
        self.dial.setFixedSize(72, 72)
        lay.addWidget(self.dial)
        self.spin = QDoubleSpinBox()
        self.spin.setRange(-180.0, 180.0);
        self.spin.setDecimals(4)
        self.spin.setKeyboardTracking(False)
        self.spin.setSingleStep(1.0);
        self.spin.setValue(0.0)
        self.spin.setAlignment(Qt.AlignCenter);
        self.spin.setFixedWidth(110)
        self.spin.setSuffix(u" °");
        lay.addWidget(self.spin)
        self.btn_reset = QPushButton(u"↺");
        self.btn_reset.setFixedSize(22, 22)
        lay.addWidget(self.btn_reset)
        lay.addStretch(1)
        self.dial.valueChanged.connect(self._on_dial_changed)
        self.spin.valueChanged.connect(self._on_spin_changed)
        self.btn_reset.clicked.connect(self._on_reset)

    def _on_dial_changed(self, v):
        self.spin.blockSignals(True);
        self.spin.setValue(v);
        self.spin.blockSignals(False)
        self.valueChanged.emit(v)

    def _on_spin_changed(self, v):
        self.dial.set_value(v);
        self.valueChanged.emit(v)

    def _on_reset(self):
        self.dial.set_value(0.0)
        self.spin.blockSignals(True);
        self.spin.setValue(0.0);
        self.spin.blockSignals(False)
        self.valueChanged.emit(0.0)

    def value(self): return self.dial.value()

    def set_value(self, v):
        self.dial.blockSignals(True);
        self.dial.set_value(v);
        self.dial.blockSignals(False)
        self.spin.blockSignals(True);
        self.spin.setValue(float(v));
        self.spin.blockSignals(False)


class SpeedKnob(QWidget):
    speedChanged = pyqtSignal(str, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2);
        lay.setSpacing(8)
        title = QLabel(u"Speed")
        f = title.font();
        f.setBold(True);
        title.setFont(f)
        title.setFixedWidth(50);
        lay.addWidget(title)
        self.combo = QComboBox()
        self.combo.addItems(['GS', 'TAS', 'IAS'])
        self.combo.setFixedWidth(70)
        lay.addWidget(self.combo)
        self.spin = QDoubleSpinBox()
        self.spin.setRange(-100.0, 2000.0);
        self.spin.setDecimals(4)
        self.spin.setKeyboardTracking(False)
        self.spin.setSingleStep(0.5);
        self.spin.setValue(0.0)
        self.spin.setAlignment(Qt.AlignCenter);
        self.spin.setFixedWidth(120)
        self.spin.setSuffix(u" m/s")
        lay.addWidget(self.spin)
        self.btn_reset = QPushButton(u"↺");
        self.btn_reset.setFixedSize(22, 22)
        lay.addWidget(self.btn_reset)
        lay.addStretch(1)
        self.combo.currentTextChanged.connect(self._on_combo_changed)
        self.spin.valueChanged.connect(self._on_spin_changed)
        self.btn_reset.clicked.connect(self._on_reset)
        self._updating = False
        self._values = {'GS': 0.0, 'TAS': 0.0, 'IAS': 0.0}
        self._cur_key = 'GS'

    def _on_combo_changed(self, key):
        if self._updating: return
        self._cur_key = key
        self._updating = True
        self.spin.setValue(self._values.get(key, 0.0))
        self._updating = False

    def _on_spin_changed(self, v):
        if self._updating: return
        self._values[self._cur_key] = float(v)
        self.speedChanged.emit(self._cur_key, float(v))

    def _on_reset(self):
        self._updating = True
        self.spin.setValue(0.0)
        self._updating = False
        self._values[self._cur_key] = 0.0
        self.speedChanged.emit(self._cur_key, 0.0)

    def set_values(self, d):
        self._updating = True
        for k in ('GS', 'TAS', 'IAS'):
            if k in d: self._values[k] = float(d[k])
        self.spin.setValue(self._values.get(self._cur_key, 0.0))
        self._updating = False


class TimeControl(QWidget):
    timeReset = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._time = 0.0
        self._speed = 1.0

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2);
        lay.setSpacing(2)

        r1 = QHBoxLayout();
        r1.setSpacing(4)
        self.chk = QCheckBox(u"运行测试")
        f = self.chk.font();
        f.setBold(True);
        self.chk.setFont(f)
        self.chk.setToolTip(_L(
            u"开启后 sum()/rate() 等函数随时间变化",
            u"When ON, sum()/rate() etc. advance with time"))
        r1.addWidget(self.chk);
        r1.addStretch(1)
        self.btn_reset = QPushButton(u"↺");
        self.btn_reset.setFixedSize(22, 22)
        self.btn_reset.setToolTip(_L(
            u"时间归 0（同时清空函数状态）",
            u"Reset time to 0 (also clears function state)"))
        r1.addWidget(self.btn_reset)
        lay.addLayout(r1)

        r2 = QHBoxLayout();
        r2.setSpacing(4)
        self.spin_time = QDoubleSpinBox()
        self.spin_time.setRange(0.0, 999999.0);
        self.spin_time.setDecimals(4)
        self.spin_time.setKeyboardTracking(False)
        self.spin_time.setSingleStep(0.01);
        self.spin_time.setValue(0.0)
        self.spin_time.setSuffix(u" 秒")
        self.spin_time.setFixedWidth(120)
        # ★ 纯显示，不可编辑
        self.spin_time.setReadOnly(True)
        self.spin_time.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.spin_time.setFocusPolicy(Qt.NoFocus)
        r2.addWidget(self.spin_time)

        self.spin_speed = QDoubleSpinBox()
        self.spin_speed.setRange(0.1, 10.0);
        self.spin_speed.setDecimals(4)  # ★ 去掉负值
        self.spin_speed.setKeyboardTracking(False)
        self.spin_speed.setSingleStep(0.1);
        self.spin_speed.setValue(1.0)
        self.spin_speed.setSuffix(u"x");
        self.spin_speed.setFixedWidth(80)
        r2.addWidget(self.spin_speed)
        lay.addLayout(r2)

        self.btn_reset.clicked.connect(self._on_reset)

    def _on_reset(self):
        # 时间归 0
        self._time = 0.0
        self.spin_time.blockSignals(True)
        self.spin_time.setValue(0.0)
        self.spin_time.blockSignals(False)
        # ★ 关闭"运行测试"勾选（阻塞信号防止递归）
        self.chk.blockSignals(True)
        self.chk.setChecked(False)
        self.chk.blockSignals(False)
        # 通知主窗口
        self.timeReset.emit()

    def value(self):
        return self._time

    def set_time(self, v):
        self._time = max(0.0, float(v))
        self.spin_time.blockSignals(True)
        self.spin_time.setValue(self._time)
        self.spin_time.blockSignals(False)


class AttitudeIndicator(QWidget):
    """飞机姿态仪表：上蓝下棕，实时显示 PitchAngle / RollAngle"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pitch = 0.0
        self._roll = 0.0
        self.setFixedSize(100, 125)

    def set_attitude(self, pitch, roll):
        self._pitch = max(-90.0, min(90.0, float(pitch)))
        self._roll = max(-90.0, min(90.0, float(roll)))
        self.update()

    def paintEvent(self, e):
        from PyQt5.QtGui import QPainterPath
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        ry = cy - 2
        radius = 16

        # 裁剪为圆角矩形
        path = QPainterPath()
        path.addRoundedRect(QRectF(2, 2, w - 4, h - 4), radius, radius)
        p.setClipPath(path)

        # 地平线旋转 + 平移
        p.save()
        p.translate(cx, cy)
        p.rotate(-self._roll)
        px_per_deg = ry / 45.0
        pitch_px = self._pitch * px_per_deg

        # 天空（上蓝）
        p.fillRect(QRectF(-w * 3, -h * 3 + pitch_px, w * 6, h * 3),
                   QColor("#2f6fb0"))
        # 地面（下棕）
        p.fillRect(QRectF(-w * 3, pitch_px, w * 6, h * 3),
                   QColor("#8a5a2a"))
        # 地平线
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.drawLine(QPointF(-w * 3, pitch_px), QPointF(w * 3, pitch_px))

        # 10 度一格刻度
        p.setPen(QPen(QColor("#ffffff"), 1))
        for deg in range(-80, 81, 10):
            if deg == 0: continue
            y = pitch_px - deg * px_per_deg
            if deg % 30 == 0:
                half = 20
            elif deg % 20 == 0:
                half = 13
            else:
                half = 7
            p.drawLine(QPointF(-half, y), QPointF(half, y))
            if deg % 30 == 0:
                p.drawText(QPointF(half + 3, y + 4), str(abs(deg)))
        p.restore()
        p.setClipping(False)

        # 中心飞机符号
        p.setPen(QPen(QColor("#ffcc00"), 3))
        p.drawLine(QPointF(cx - 24, cy), QPointF(cx - 8, cy))
        p.drawLine(QPointF(cx + 8, cy), QPointF(cx + 24, cy))
        p.drawLine(QPointF(cx - 8, cy), QPointF(cx, cy + 6))
        p.drawLine(QPointF(cx + 8, cy), QPointF(cx, cy + 6))

        # 外框
        p.setPen(QPen(QColor("#555555"), 2))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(2, 2, w - 4, h - 4), radius, radius)

        # 顶部滚转指示三角
        p.setBrush(QBrush(QColor("#ffcc00")))
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([
            QPointF(cx, 4),
            QPointF(cx - 5, 12),
            QPointF(cx + 5, 12),
        ]))


class _JoystickArea(QWidget):
    valueChanged = pyqtSignal(float, float)
    AXIS_SNAP = 0.08      # 轴吸附触发阈值 ±8%
    AXIS_RELEASE = 0.12   # 脱离吸附的阈值（防抖，比触发值大）

    def __init__(self, parent=None, auto_center=False, snap_axis=False):
        super().__init__(parent)
        self._x = 0.0
        self._y = 0.0
        self._dragging = False
        self._auto_center = bool(auto_center)
        self._axis_snap = bool(snap_axis)
        self._lock_x = False   # 是否已吸附在 X 轴
        self._lock_y = False   # 是否已吸附在 Y 轴
        self.setFixedSize(110, 110)
        self.setCursor(Qt.CrossCursor)

    def x(self):
        return self._x

    def y(self):
        return self._y

    def set_value(self, x, y):
        self._x = max(-1.0, min(1.0, float(x)))
        self._y = max(-1.0, min(1.0, float(y)))
        self.update();
        self.valueChanged.emit(self._x, self._y)

    def paintEvent(self, e):
        p = QPainter(self);
        p.setRenderHint(QPainter.Antialiasing, True)
        w = self.width();
        h = self.height();
        m = 2
        rect = QRectF(m, m, w - 2 * m, h - 2 * m)
        p.setPen(QPen(QColor("#888"), 2));
        p.setBrush(QBrush(QColor("#2a2a2a")))
        p.drawRoundedRect(rect, 10, 10)
        cx = w / 2.0;
        cy = h / 2.0
        p.setPen(QPen(QColor("#555"), 1, Qt.DashLine))
        p.drawLine(QPointF(rect.left() + 6, cy), QPointF(rect.right() - 6, cy))
        p.drawLine(QPointF(cx, rect.top() + 6), QPointF(cx, rect.bottom() - 6))
        mm = 14;
        rx = cx - mm;
        ry = cy - mm
        kx = cx + self._x * rx;
        ky = cy - self._y * ry
        p.setPen(QPen(QColor("#00a0ff"), 2));
        p.setBrush(QBrush(QColor("#00a0ff")))
        p.drawEllipse(QPointF(kx, ky), 9, 9)

    def _update_from_pos(self, pos):
        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0
        mm = 14
        rx = cx - mm
        ry = cy - mm
        dx = (pos.x() - cx) / rx
        dy = (pos.y() - cy) / ry
        dx = max(-1.0, min(1.0, dx))
        dy = max(-1.0, min(1.0, dy))
        # ★ 轴吸附（带粘性）：
        #   · 进入 ±8% 区间 → 吸到 0
        #   · 吸住后必须移出 ±12% 才会脱离，防止抖动
        if self._axis_snap:
            # X 轴
            if self._lock_x:
                if abs(dx) < self.AXIS_RELEASE:
                    dx = 0.0
                else:
                    self._lock_x = False
            if not self._lock_x and abs(dx) < self.AXIS_SNAP:
                dx = 0.0
                self._lock_x = True
            # Y 轴
            if self._lock_y:
                if abs(dy) < self.AXIS_RELEASE:
                    dy = 0.0
                else:
                    self._lock_y = False
            if not self._lock_y and abs(dy) < self.AXIS_SNAP:
                dy = 0.0
                self._lock_y = True
        self.set_value(dx, -dy)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._dragging = True;
            self._update_from_pos(e.pos())

    def mouseMoveEvent(self, e):
        if self._dragging: self._update_from_pos(e.pos())

    def mouseReleaseEvent(self, e):
        self._dragging = False
        self._lock_x = False
        self._lock_y = False
        if self._auto_center:
            self.set_value(0.0, 0.0)


JOY_LABEL_FULL = {
    'Trl': 'Throttle',
    'Yaw': 'Yaw',
    'Brk': 'Brake',
    'Pth': 'Pitch',
    'Rol': 'Roll',
}


class VirtualJoystick(QWidget):
    valueChanged = pyqtSignal()

    def __init__(self, name, side='left', fields=None, parent=None,
                 auto_center=False, on_reset=None, snap_axis=False):
        super().__init__(parent)
        if fields is None: fields = []
        outer = QHBoxLayout(self)
        outer.setContentsMargins(2, 2, 2, 2);
        outer.setSpacing(4)
        self.btn_reset = QPushButton(u"↺")
        self.btn_reset.setFixedSize(22, 22)
        fb = self.btn_reset.font();
        fb.setPointSize(9);
        self.btn_reset.setFont(fb)
        center = QWidget()
        clay = QVBoxLayout(center);
        clay.setContentsMargins(0, 0, 0, 0);
        clay.setSpacing(2)
        title = QLabel(name);
        title.setAlignment(Qt.AlignCenter)
        ft = title.font();
        ft.setBold(True);
        title.setFont(ft);
        clay.addWidget(title)
        self.area = _JoystickArea(self, auto_center=auto_center,
                                  snap_axis=snap_axis)
        clay.addWidget(self.area, 1, Qt.AlignCenter)
        self.value_col = QWidget()
        vcl = QVBoxLayout(self.value_col);
        vcl.setContentsMargins(0, 0, 0, 0)
        vcl.setSpacing(2);
        vcl.addStretch(1)
        self.field_spins = {}
        for fname, lo, hi in fields:
            row = QHBoxLayout();
            row.setContentsMargins(0, 0, 0, 0);
            row.setSpacing(2)
            lbl = QLabel(JOY_LABEL_FULL.get(fname, fname))
            fl = lbl.font();
            fl.setPointSize(8);
            fl.setBold(True);
            lbl.setFont(fl)
            lbl.setStyleSheet("color: #000000;");
            lbl.setFixedWidth(58)
            row.addWidget(lbl)
            sp = QDoubleSpinBox()
            sp.setRange(lo, hi);
            sp.setDecimals(0);
            sp.setKeyboardTracking(False)
            sp.setSingleStep(1)
            sp.setValue(0);
            sp.setSuffix(u"%");
            sp.setAlignment(Qt.AlignCenter)
            sp.setFixedWidth(48);
            sp.setStyleSheet("color: #000000;")
            row.addWidget(sp)
            self.field_spins[fname] = sp
            vcl.addLayout(row)
        vcl.addStretch(1)
        if not fields:
            self.value_col.setVisible(False)
        if side == 'left':
            outer.addWidget(self.value_col, 0, Qt.AlignVCenter)
            outer.addWidget(self.btn_reset, 0, Qt.AlignVCenter)
            outer.addWidget(center, 1)
        else:
            outer.addWidget(center, 1)
            outer.addWidget(self.btn_reset, 0, Qt.AlignVCenter)
            outer.addWidget(self.value_col, 0, Qt.AlignVCenter)
        self.side = side;
        self._forced = {}
        self.btn_reset.clicked.connect(self.reset)
        if on_reset is not None:
            self.btn_reset.clicked.connect(on_reset)
        self.area.valueChanged.connect(self._on_area_changed)
        for fname, sp in self.field_spins.items():
            sp.valueChanged.connect(lambda _, k=fname: self._on_spin_changed(k))

    def _on_area_changed(self, x, y):
        self._sync_spins_from_area();
        self.valueChanged.emit()

    def _sync_spins_from_area(self):
        for fname, sp in self.field_spins.items():
            sp.blockSignals(True)
            if fname in self._forced:
                sp.setValue(int(self._forced[fname]));
                sp.blockSignals(False);
                continue
            if fname == 'Yaw':
                sp.setValue(max(-100, min(100, int(round(self.area.x() * 100)))))
            elif fname == 'Trl':
                sp.setValue(int(round(max(0, self.area.y()) * 100)))
            elif fname == 'Brk':
                sp.setValue(int(round(max(0, -self.area.y()) * 100)))
            elif fname == 'Pth':
                sp.setValue(int(round(self.area.y() * 100)))
            elif fname == 'Rol':
                sp.setValue(int(round(self.area.x() * 100)))
            sp.blockSignals(False)

    def _on_spin_changed(self, key):
        if key in self._forced:
            self._sync_spins_from_area();
            return
        sp = self.field_spins.get(key)
        if sp is None: return
        v = sp.value() / 100.0
        x = self.area.x();
        y = self.area.y()
        if key == 'Yaw':
            x = v
        elif key == 'Trl':
            y = max(0.0, v)
        elif key == 'Brk':
            y = -max(0.0, v)
        elif key == 'Pth':
            y = v
        elif key == 'Rol':
            x = v
        self.area.blockSignals(True)
        self.area._x = max(-1.0, min(1.0, x))
        self.area._y = max(-1.0, min(1.0, y))
        self.area.update();
        self.area.blockSignals(False)
        self.valueChanged.emit()

    def reset(self):
        self.area.set_value(0.0, 0.0)

    def x(self):
        return self.area.x()

    def y(self):
        return self.area.y()

    def set_value(self, x, y):
        self.area.set_value(x, y)

    def set_forced_value(self, key, value):
        if value is None:
            self._forced.pop(key, None)
        else:
            self._forced[key] = int(value)
        self._sync_spins_from_area();
        self.valueChanged.emit()


# ==================================================== 对话框
class VarListDialog(QDialog):
    def __init__(self, variables, parent=None, custom_names=None):
        super().__init__(parent)
        self.setWindowTitle(_T('var_list_title'));
        self.resize(420, 560)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        v = QVBoxLayout(self)
        v.addWidget(QLabel(_T('var_list_hint')))
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([_T('var_name_col'), _T('cur_val_col')])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        seen = set()
        for name in CONTROL_VARS + FLIGHT_VARS + ['pi', 'e']:
            if name in seen: continue
            seen.add(name)
            r = self.table.rowCount();
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(name))
            self.table.setItem(r, 1, QTableWidgetItem(_fmt_num(variables.get(name, 0))))
        # ★ 玩家自定义变量（带 ★ 前缀）
        for name in (custom_names or []):
            if name in seen: continue
            seen.add(name)
            r = self.table.rowCount(); self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(u"★ " + name))
            self.table.setItem(r, 1, QTableWidgetItem(_fmt_num(variables.get(name, 0))))
        v.addWidget(self.table)
        row = QHBoxLayout()
        bc = QPushButton(_T('copy_all'));
        bcl = QPushButton(_T('close'))
        row.addStretch(1);
        row.addWidget(bc);
        row.addWidget(bcl);
        v.addLayout(row)

        def do_copy():
            lines = [u"{%s}" % self.table.item(r, 0).text()
                     for r in range(self.table.rowCount())]
            QGuiApplication.clipboard().setText(u" ".join(lines))
            bc.setText(_T('copied'))

        bc.clicked.connect(do_copy);
        bcl.clicked.connect(self.accept)


class FlightDataDialog(QDialog):
    valueChanged = pyqtSignal(str, float)
    resetOneRequested = pyqtSignal(str)
    resetAllRequested = pyqtSignal()
    closed = pyqtSignal()

    CTRL_FIELDS = [
        ('Throttle', 0.0, 1.0, 0.0),
        ('Yaw', -1.0, 1.0, 0.0),
        ('Pitch', -1.0, 1.0, 0.0),
        ('Roll', -1.0, 1.0, 0.0),
        ('Brake', 0.0, 1.0, 0.0),
        ('Heading', -180.0, 180.0, 0.0),
        ('VTOL', -1.0, 1.0, 0.0),
        ('Trim', -1.0, 1.0, 0.0),
    ]
    FLIGHT_FIELDS = [
        ('Altitude', -1000.0, 20000.0, 0.0),
        ('AltitudeAgl', -1000.0, 20000.0, 0.0),
        ('GS', -100.0, 2000.0, 0.0),
        ('IAS', -100.0, 2000.0, 0.0),
        ('TAS', -100.0, 2000.0, 0.0),
        ('Fuel', 0.0, 1.0, 1.0),
        ('AngleOfAttack', -180.0, 180.0, 0.0),
        ('AngleOfSlip', -180.0, 180.0, 0.0),
        ('PitchAngle', -180.0, 180.0, 0.0),
        ('RollAngle', -180.0, 180.0, 0.0),
        ('GForce', -20.0, 20.0, 0.0),
        ('VerticalG', -20.0, 20.0, 0.0),
        ('Latitude', -100000.0, 100000.0, 0.0),
        ('Longitude', -100000.0, 100000.0, 0.0),
        # ★ 新增
        ('PitchRate', -180.0, 180.0, 0.0),
        ('YawRate', -180.0, 180.0, 0.0),
        ('RollRate', -180.0, 180.0, 0.0),
        ('TargetHeading', -180.0, 180.0, 0.0),
        ('TargetElevation', -90.0, 90.0, 0.0),
        ('TargetDistance', 0.0, 100000.0, 0.0),
        ('TargetSelected', 0.0, 1.0, 0.0),
        ('TargetLocked', 0.0, 1.0, 0.0),
        ('TargetLocking', 0.0, 1.0, 0.0),
        ('SelectedWeapon', 0.0, 100.0, 0.0),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_T('flight_title'))
        self.resize(480, 720)
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint |
                            Qt.WindowCloseButtonHint)
        self.setModal(False)
        self._updating = False
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(8, 8, 8, 8);
        main_lay.setSpacing(6)
        top = QHBoxLayout()
        top.addStretch(1)
        self.btn_reset_all = QPushButton(u"↺ " + _T('reset_all'))
        self.btn_reset_all.setFixedHeight(24)
        self.btn_reset_all.clicked.connect(self.resetAllRequested.emit)
        top.addWidget(self.btn_reset_all)
        main_lay.addLayout(top)
        scroll = QScrollArea();
        scroll.setWidgetResizable(True)
        inner = QWidget();
        form = QVBoxLayout(inner)
        form.setContentsMargins(0, 0, 0, 0);
        form.setSpacing(6)
        self.spins = {}

        def make_group(title, fields):
            gb = QGroupBox(title)
            gf = QFormLayout(gb)
            gf.setLabelAlignment(Qt.AlignRight)
            for name, lo, hi, default in fields:
                row = QWidget();
                h = QHBoxLayout(row)
                h.setContentsMargins(0, 0, 0, 0);
                h.setSpacing(4)
                sp = QDoubleSpinBox()
                sp.setRange(lo, hi);
                sp.setDecimals(4)
                sp.setKeyboardTracking(False)
                sp.setSingleStep(0.1 if hi - lo <= 10 else 1.0)
                sp.setValue(default);
                sp.setMinimumWidth(130)
                h.addWidget(sp, 1)
                btn = QPushButton(u"↺");
                btn.setFixedSize(22, 22)
                btn.setToolTip(_T('reset_one') + u" " + name)
                h.addWidget(btn)
                gf.addRow(name, row)
                self.spins[name] = sp
                sp.valueChanged.connect(lambda v, n=name: self._on_spin_changed(n, v))
                btn.clicked.connect(lambda _, n=name: self.resetOneRequested.emit(n))
            return gb

        form.addWidget(make_group(_T('ctrl_section'), self.CTRL_FIELDS))
        form.addWidget(make_group(_T('flight_section'), self.FLIGHT_FIELDS))
        form.addStretch(1)
        scroll.setWidget(inner)
        main_lay.addWidget(scroll, 1)
        bottom = QHBoxLayout();
        bottom.addStretch(1)
        btn_close = QPushButton(_T('close'))
        btn_close.clicked.connect(self.close)
        bottom.addWidget(btn_close)
        main_lay.addLayout(bottom)

    def _on_spin_changed(self, key, v):
        if self._updating: return
        self.valueChanged.emit(key, float(v))

    def set_values(self, d):
        self._updating = True
        for k, sp in self.spins.items():
            if k in d:
                try:
                    sp.blockSignals(True);
                    sp.setValue(float(d[k]));
                    sp.blockSignals(False)
                except Exception:
                    pass
        self._updating = False

    def set_one(self, key, v):
        sp = self.spins.get(key)
        if sp is None: return
        self._updating = True
        sp.blockSignals(True);
        sp.setValue(float(v));
        sp.blockSignals(False)
        self._updating = False

    def get_values(self):
        return {k: sp.value() for k, sp in self.spins.items()}

    def closeEvent(self, e):
        self.closed.emit();
        super().closeEvent(e)


class FloatingControlPanel(QWidget):
    dockRequested = pyqtSignal()
    showFlightDataRequested = pyqtSignal()
    showCustomVarsRequested = pyqtSignal()
    showTargetCtrlRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(None)
        self.setWindowTitle(_T('float_title'))
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint |
                            Qt.WindowCloseButtonHint | Qt.WindowMaximizeButtonHint)
        self.resize(820, 470)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4);
        lay.setSpacing(4)
        bar = QHBoxLayout()
        self.btn_flight_data = QPushButton(_T('flight_data_btn'))
        self.btn_flight_data.setFixedHeight(24)
        self.btn_flight_data.clicked.connect(self.showFlightDataRequested.emit)
        bar.addWidget(self.btn_flight_data)
        self.btn_custom_vars = QPushButton(_T('custom_vars_btn'))
        self.btn_custom_vars.setFixedHeight(24)
        self.btn_custom_vars.clicked.connect(self.showCustomVarsRequested.emit)
        bar.addWidget(self.btn_custom_vars)
        self.btn_target_ctrl = QPushButton(_T('target_ctrl_btn'))
        self.btn_target_ctrl.setFixedHeight(24)
        self.btn_target_ctrl.clicked.connect(self.showTargetCtrlRequested.emit)
        bar.addWidget(self.btn_target_ctrl)
        bar.addStretch(1)
        self.btn_dock = QPushButton(_T('dock_btn'))
        self.btn_dock.setFixedHeight(24)
        self.btn_dock.clicked.connect(self.dockRequested.emit)
        bar.addWidget(self.btn_dock)
        lay.addLayout(bar)
        self._container = QWidget()
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._container, 1)
        self.aoa_knob = AoAKnob()
        self.speed_knob = SpeedKnob()

    def take_widget(self, w):
        w.setParent(None);
        self._container_layout.addWidget(w)

    def release_widget(self):
        if self._container_layout.count() > 0:
            w = self._container_layout.itemAt(0).widget()
            self._container_layout.removeWidget(w);
            w.setParent(None)
            return w
        return None

    def closeEvent(self, e):
        self.dockRequested.emit();
        super().closeEvent(e)


# ============================================================== 主窗口
class MainWindow(QMainWindow):
    def _on_compensate_toggled(self, checked):
        for it in self.canvas.items:
            it.compensate_offset = bool(checked)
        # ★ 补偿开关影响 special 分支 → 需要重新求值 + 刷新画布
        self.canvas.eval_all(0.0)
        self.canvas.update()
        # 蓝框形状/位置也变了，同时刷新属性面板的范围与预览
        try:
            self.panel.refresh_preview()
        except Exception:
            pass
        self.refresh_output()

    def __init__(self):
        super().__init__()
        self.setWindowTitle(_T('title') + u"  " + APP_VERSION)
        self._flight_data = {
            'Altitude': 0.0, 'AltitudeAgl': 0.0, 'GS': 0.0, 'IAS': 0.0,
            'TAS': 0.0, 'Fuel': 1.0, 'AngleOfAttack': 0.0, 'AngleOfSlip': 0.0,
            'PitchAngle': 0.0, 'RollAngle': 0.0, 'Heading': 0.0, 'Time': 0.0,
            'GForce': 0.0, 'VerticalG': 0.0, 'Latitude': 0.0, 'Longitude': 0.0,
            # ★ 新增
            'PitchRate': 0.0, 'YawRate': 0.0, 'RollRate': 0.0,
            'TargetHeading': 0.0, 'TargetElevation': 0.0,
            'TargetDistance': 0.0, 'TargetSelected': 0.0,
            'TargetLocked': 0.0, 'TargetLocking': 0.0,
            'SelectedWeapon': 0.0,
        }
        # ★ 玩家自定义变量（玩家起名 + 滑块调节）
        self._custom_vars = []           # list[dict]
        self._custom_vars_dlg = None
        self._target_dlg = None
        # ★ 目标控制窗口的 3D 场景状态（关闭对话框后仍保留）
        self._target_scene_state = None
        self.canvas = Canvas()
        self.panel = PropertyPanel(self.canvas)
        self.charlist = CharListPanel(self.canvas)

        right = QSplitter(Qt.Vertical)
        right.setChildrenCollapsible(True);
        right.setHandleWidth(2)
        right.setStyleSheet(
            "QSplitter::handle { background-color: #4a4a4a; border: 1px solid #2a2a2a; }"
            "QSplitter::handle:hover { background-color: #00a0ff; }")
        right.addWidget(self.panel);
        right.addWidget(self.charlist)
        right.setStretchFactor(0, 1);
        right.setStretchFactor(1, 0)
        right.setSizes([700, 190]);
        self._right_split = right

        top_split = QSplitter(Qt.Horizontal)
        top_split.addWidget(self.canvas);
        top_split.addWidget(right)
        top_split.setStretchFactor(0, 1);
        top_split.setStretchFactor(1, 0)
        top_split.setSizes([740, 260])

        bottom = QSplitter(Qt.Horizontal)
        bottom.setChildrenCollapsible(True);
        bottom.setHandleWidth(2)
        bottom.setStyleSheet(
            "QSplitter::handle { background-color: #4a4a4a; border: 1px solid #2a2a2a; }"
            "QSplitter::handle:hover { background-color: #00a0ff; }")

        left = QWidget();
        left.setObjectName("leftOutput")
        self._left_widget = left
        llay = QVBoxLayout(left);
        llay.setContentsMargins(6, 4, 6, 6);
        llay.setSpacing(4)
        self._left_top_spacer = QWidget()
        self._left_top_spacer.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)
        self._left_top_spacer.setVisible(False)
        llay.addWidget(self._left_top_spacer)

        self._output_split = QSplitter(Qt.Horizontal)
        self._output_split.setChildrenCollapsible(False)
        self._output_split.setHandleWidth(3)
        self._output_split.setStyleSheet(
            "QSplitter::handle { background-color: #4a4a4a; }"
            "QSplitter::handle:hover { background-color: #00a0ff; }")

        # ---- 左侧：输出标题栏 + 输出文本框 ----
        out_container = QWidget()
        out_lay = QVBoxLayout(out_container)
        out_lay.setContentsMargins(0, 0, 0, 0);
        out_lay.setSpacing(2)
        header = QHBoxLayout()
        self.output_title_label = QLabel(_T('output_title'))
        header.addWidget(self.output_title_label)
        # ★ 备用位置：当控制面板最小化 + 自定义函数面板也隐藏时，
        #   把"显示控制面板"按钮放到这里
        self.btn_show_ctrl_out = QPushButton(
            _L(u"▲ 显示控制面板", u"▲ Show Control Panel"))
        self.btn_show_ctrl_out.setFixedHeight(20)
        self.btn_show_ctrl_out.setVisible(False)
        self.btn_show_ctrl_out.setToolTip(_L(
            u"控制面板已最小化，点击可恢复显示",
            u"Control panel is minimized; click to restore"))
        self.btn_show_ctrl_out.clicked.connect(self._show_ctrl_from_var)
        header.addWidget(self.btn_show_ctrl_out)
        header.addStretch(1)
        # ★ 四个按钮 2×2 网格（右上角两行两列）
        btn_grid = QGridLayout()
        btn_grid.setContentsMargins(0, 0, 0, 0)
        btn_grid.setSpacing(2)
        self.chk_autoupdate = QCheckBox(_T('auto_refresh'))
        self.chk_autoupdate.setChecked(True)
        # ★ 自定义变量按钮（按下显示窗口，弹起关闭窗口）
        self.btn_custom_vars = QPushButton(_T('custom_vars_btn'))
        self.btn_custom_vars.setCheckable(True)
        self.btn_custom_vars.setChecked(True)
        self.btn_custom_vars.toggled.connect(self._on_custom_vars_toggled)
        self.btn_copy = QPushButton(_T('copy'))
        self.btn_copy.clicked.connect(self.copy_output)
        self.btn_min = QPushButton(_T('minimize'))
        self.btn_min.clicked.connect(self._toggle_output_min)
        # ★ CSE 压缩档位数据（下拉已移到右侧“自定义函数”面板头部）
        self._cse_level = 'mid'
        btn_grid.addWidget(self.chk_autoupdate,    0, 0)
        btn_grid.addWidget(self.btn_custom_vars,   0, 1)
        btn_grid.addWidget(self.btn_copy,          1, 0)
        btn_grid.addWidget(self.btn_min,           1, 1)
        for b in (self.chk_autoupdate, self.btn_custom_vars,
                  self.btn_copy, self.btn_min):
            b.setMinimumWidth(78)
        header.addLayout(btn_grid)
        out_lay.addLayout(header)
        self.output_edit = QPlainTextEdit();
        self.output_edit.setReadOnly(True)
        self.output_edit.setLineWrapMode(QPlainTextEdit.NoWrap)
        f = QFont("Consolas");
        f.setPointSize(8);
        self.output_edit.setFont(f)
        out_lay.addWidget(self.output_edit, 1)
        self._output_split.addWidget(out_container)

        # ---- 右侧：自定义变量表 ----
        var_wrap = QWidget()
        var_wrap.setMinimumWidth(200)
        self._var_wrap = var_wrap
        vlay = QVBoxLayout(var_wrap)
        vlay.setContentsMargins(0, 0, 0, 0);
        vlay.setSpacing(2)
        vhdr = QHBoxLayout()
        # ★ 控制面板最小化时出现的“显示控制面板”按钮
        self.btn_show_ctrl = QPushButton(
            _L(u"▲ 显示控制面板", u"▲ Show Control Panel"))
        self.btn_show_ctrl.setFixedHeight(20)
        self.btn_show_ctrl.setVisible(False)
        self.btn_show_ctrl.setToolTip(_L(
            u"控制面板已最小化，点击可恢复显示",
            u"Control panel is minimized; click to restore"))
        self.btn_show_ctrl.clicked.connect(self._show_ctrl_from_var)
        vhdr.addWidget(self.btn_show_ctrl)
        self.lbl_custom_vars = QLabel(_T('custom_vars_hdr'))
        vhdr.addWidget(self.lbl_custom_vars)
        # ★ 变量名前缀输入框（默认 V）
        self.edit_var_prefix = QLineEdit(u"V")
        self.edit_var_prefix.setFixedWidth(60)
        self.edit_var_prefix.setMaxLength(16)
        self.edit_var_prefix.setPlaceholderText(u"V")
        self.edit_var_prefix.setToolTip(_L(
            u"自定义函数变量的前缀\n"
            u"留空时使用默认 V（V1、V2、V3…）\n"
            u"例如输入 abc → abc1、abc2、abc3…\n"
            u"只允许字母 / 数字 / 下划线；不能与现有变量或函数重名",
            u"Prefix for custom variable names\n"
            u"Empty = default V (V1, V2, V3…)\n"
            u"e.g. 'abc' → abc1, abc2, abc3…\n"
            u"Only letters / digits / underscore; must not clash with "
            u"existing variables or functions"))
        # ★ 实时过滤非法字符 + 红框冲突校验
        self.edit_var_prefix.textChanged.connect(
            self._on_var_prefix_text_changed)
        self.edit_var_prefix.editingFinished.connect(
            lambda: self._on_var_prefix_changed())
        vhdr.addWidget(self.edit_var_prefix)
        vhdr.addStretch(1)
        # ★ 压缩程度（低 / 中 / 高）
        self.lbl_cse_level = QLabel(_T('cse_label'))
        vhdr.addWidget(self.lbl_cse_level)
        self.cmb_cse_level = QComboBox()
        self.cmb_cse_level.addItem(_T('cse_low'), 'low')
        self.cmb_cse_level.addItem(_T('cse_mid'), 'mid')
        self.cmb_cse_level.addItem(_T('cse_high'), 'high')
        self.cmb_cse_level.setCurrentIndex(1)   # 默认中档
        self.cmb_cse_level.setFixedWidth(60)
        self.cmb_cse_level.setToolTip(_T('cse_tip'))
        self.cmb_cse_level.currentIndexChanged.connect(
            lambda _: self._on_cse_level_changed())
        vhdr.addWidget(self.cmb_cse_level)
        vlay.addLayout(vhdr)
        self.var_table = QTableWidget(0, 0)
        self.var_table.verticalHeader().setVisible(False)
        self.var_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.var_table.itemChanged.connect(self._on_var_item_changed)
        f2 = QFont("Consolas");
        f2.setPointSize(8);
        self.var_table.setFont(f2)
        vlay.addWidget(self.var_table)
        self._output_split.addWidget(var_wrap)
        # ★ 自适应列组
        self._var_cols = 1
        self._var_resize_timer = QTimer(self)
        self._var_resize_timer.setSingleShot(True)
        self._var_resize_timer.setInterval(180)
        self._var_resize_timer.timeout.connect(self._refresh_var_layout)
        self.var_table.viewport().installEventFilter(self)

        self._output_split.setStretchFactor(0, 1)
        self._output_split.setStretchFactor(1, 3)
        # ★ 拖动分割条 → 重排列数
        self._output_split.splitterMoved.connect(
            lambda *_: self._var_resize_timer.start())
        # ★ 延迟设置初始比例（等布局完成后再设，否则会被忽略）
        QTimer.singleShot(0, lambda: self._output_split.setSizes([220, 640]))
        llay.addWidget(self._output_split)

        ctrl = QWidget();
        ctrl.setMinimumWidth(740)
        ctrl_layout = QVBoxLayout(ctrl)
        ctrl_layout.setContentsMargins(4, 4, 4, 4);
        ctrl_layout.setSpacing(6)
        self._ctrl_layout = ctrl_layout

        ctrl_top_bar = QHBoxLayout()
        ctrl_top_bar.setContentsMargins(0, 0, 0, 0)

        # ★ 左上角：飞行数据 + 自定义变量（与独立控制面板保持一致）
        self.btn_flight_data_main = QPushButton(_T('flight_data_btn'))
        self.btn_flight_data_main.setFixedHeight(22)
        self.btn_flight_data_main.setToolTip(_L(
            u"打开飞行数据模拟窗口",
            u"Open flight data simulation window"))
        self.btn_flight_data_main.clicked.connect(self.show_flight_data)
        ctrl_top_bar.addWidget(self.btn_flight_data_main)

        self.btn_custom_vars_main = QPushButton(_T('custom_vars_btn'))
        self.btn_custom_vars_main.setFixedHeight(22)
        self.btn_custom_vars_main.setToolTip(_L(
            u"打开自定义变量编辑窗口（可添加/删除变量，用滑块调节）",
            u"Open custom variable editor "
            u"(add/delete variables, adjust via slider)"))
        self.btn_custom_vars_main.clicked.connect(self.show_custom_vars)
        ctrl_top_bar.addWidget(self.btn_custom_vars_main)

        # ★ 目标控制按钮（自定义变量右边）
        self.btn_target_ctrl_main = QPushButton(_T('target_ctrl_btn'))
        self.btn_target_ctrl_main.setFixedHeight(22)
        self.btn_target_ctrl_main.setToolTip(_L(
            u"打开目标控制窗口（目标航向 / 俯仰 / 距离 / 锁定状态）",
            u"Open target control "
            u"(heading / elevation / distance / lock status)"))
        self.btn_target_ctrl_main.clicked.connect(self.show_target_control)
        ctrl_top_bar.addWidget(self.btn_target_ctrl_main)

        ctrl_top_bar.addStretch(1)

        # ★ 新增：控制面板最小化按钮
        self.btn_ctrl_min = QPushButton(_T('minimize'))
        self.btn_ctrl_min.setFixedHeight(22)
        self.btn_ctrl_min.setToolTip(_L(
            u"隐藏控制面板",
            u"Hide control panel"))
        self.btn_ctrl_min.clicked.connect(self._toggle_ctrl_min)
        ctrl_top_bar.addWidget(self.btn_ctrl_min)

        self.btn_float_panel = QPushButton(_T('float_btn'))
        self.btn_float_panel.setFixedHeight(22)
        self.btn_float_panel.clicked.connect(self._toggle_float_panel)
        ctrl_top_bar.addWidget(self.btn_float_panel)
        ctrl_layout.addLayout(ctrl_top_bar)

        top_row = QHBoxLayout();
        top_row.setSpacing(12)
        self.heading_knob = HeadingKnob()
        self.time_control = TimeControl()
        top_row.addWidget(self.heading_knob, 1)
        top_row.addWidget(self.time_control, 0)
        ctrl_layout.addLayout(top_row)

        mid = QWidget()
        mid_layout = QHBoxLayout(mid)
        mid_layout.setContentsMargins(0, 0, 0, 0);
        mid_layout.setSpacing(6)
        self.slider_vtol = VerticalSlider(u"VTOL");
        mid_layout.addWidget(self.slider_vtol)
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0);
        center_layout.setSpacing(6)
        self._ctrl_center_layout = center_layout
        jrow = QHBoxLayout();
        jrow.setSpacing(10)
        self.joystick_left = VirtualJoystick(
            u"L Stick", side='left',
            fields=[('Trl', 0, 100), ('Yaw', -100, 100), ('Brk', 0, 100)],
            snap_axis=True)
        self.joystick_right = VirtualJoystick(
            u"R Stick", side='right',
            fields=[('Pth', -100, 100), ('Rol', -100, 100)],
            snap_axis=True)
        jrow.addStretch(1);
        jrow.addWidget(self.joystick_left)
        jrow.addWidget(self.joystick_right);
        jrow.addStretch(1)
        center_layout.addLayout(jrow)
        self.activate_btns = []
        grid = QGridLayout();
        grid.setSpacing(3);
        grid.setContentsMargins(0, 0, 0, 0)
        for i in range(8):
            b = ActivateButton("Activate%d" % (i + 1), default_on=(i == 7))
            self.activate_btns.append(b)
            grid.addWidget(b, i // 4, i % 4)
        center_layout.addLayout(grid)
        srow = QHBoxLayout();
        srow.setSpacing(10)
        self.landing_btn = SquareButton("LandingGear", "LandingGear",
                                        default_on=True, on_value=0, off_value=1)
        self.brake_btn = SquareButton("Brake", "Brake",
                                      default_on=False, on_value=1, off_value=0)
        srow.addStretch(1);
        srow.addWidget(self.landing_btn)
        srow.addWidget(self.brake_btn);
        srow.addStretch(1)
        center_layout.addLayout(srow)

        # ★ 姿态仪表 + 自动回中摇杆 + 角度数值框
        self._att_container = QWidget()
        att_outer = QVBoxLayout(self._att_container)
        att_outer.setContentsMargins(0, 0, 0, 0);
        att_outer.setSpacing(4)

        att_top = QHBoxLayout();
        att_top.setSpacing(8)
        att_top.addStretch(1)
        self.attitude_indicator = AttitudeIndicator()
        att_top.addWidget(self.attitude_indicator)
        self.attitude_joystick = VirtualJoystick(
            u"Attitude Stick", side='left', fields=[], auto_center=True,
            on_reset=self._reset_attitude_angles, snap_axis=True)
        att_top.addWidget(self.attitude_joystick)
        # ★ 垂直反转按钮（摇杆右侧）
        #   默认未按下 = 垂直反转（推杆低头）
        #   按下后 = 正常模式（拉杆抬头）
        self.btn_att_invert = QPushButton(u"⇅")
        self.btn_att_invert.setCheckable(True)
        self.btn_att_invert.setChecked(False)  # 默认未按下 = 反转
        self.btn_att_invert.setFixedSize(24, 24)
        self.btn_att_invert.setToolTip(_L(
            u"垂直反转（默认开启）\n"
            u"未按下：向上推 = 俯仰角减小（推杆低头）\n"
            u"按下后：向上推 = 俯仰角增大（拉杆抬头）",
            u"Invert vertical (ON by default)\n"
            u"Released: push up = pitch decreases (nose down)\n"
            u"Pressed: push up = pitch increases (nose up)"))
        att_top.addWidget(self.btn_att_invert, 0, Qt.AlignVCenter)
        att_top.addStretch(1)
        att_outer.addLayout(att_top)

        att_vals = QHBoxLayout();
        att_vals.setSpacing(6)
        att_vals.addStretch(1)
        att_vals.addWidget(QLabel(u"Pitch:"))
        self.lbl_pitch_val = QLabel(u"0.0000")
        self.lbl_pitch_val.setFixedWidth(66)
        self.lbl_pitch_val.setAlignment(Qt.AlignCenter)
        self.lbl_pitch_val.setStyleSheet(
            "border:1px solid #888; background:#ffffff; color:#000000;"
            "padding:1px 4px; font-family:Consolas;")
        att_vals.addWidget(self.lbl_pitch_val)
        att_vals.addSpacing(8)
        att_vals.addWidget(QLabel(u"Roll:"))
        self.lbl_roll_val = QLabel(u"0.0000")
        self.lbl_roll_val.setFixedWidth(66)
        self.lbl_roll_val.setAlignment(Qt.AlignCenter)
        self.lbl_roll_val.setStyleSheet(
            "border:1px solid #888; background:#ffffff; color:#000000;"
            "padding:1px 4px; font-family:Consolas;")
        att_vals.addWidget(self.lbl_roll_val)
        att_vals.addStretch(1)
        att_outer.addLayout(att_vals)

        # ★ 姿态仪容器不加入任何布局，只在独立控制面板里动态挂载
        self._att_container.setVisible(False)
        self._att_row = None

        center_layout.addStretch(1)
        mid_layout.addWidget(center, 1)
        self.slider_trim = VerticalSlider(u"Trim");
        mid_layout.addWidget(self.slider_trim)
        ctrl_layout.addWidget(mid, 1)
        self._ctrl_widget = ctrl
        self._ctrl_minimized = False

        bottom.addWidget(left);
        bottom.addWidget(ctrl)
        bottom.setStretchFactor(0, 1);
        bottom.setStretchFactor(1, 0)
        bottom.setSizes([800, 740]);
        self._bottom_split = bottom

        self.v_split = QSplitter(Qt.Vertical)
        self.v_split.setObjectName("mainVSplit")
        self.v_split.addWidget(top_split);
        self.v_split.addWidget(bottom)
        self.v_split.setChildrenCollapsible(True);
        self.v_split.setHandleWidth(2)
        self.v_split.setStyleSheet(
            "QSplitter#mainVSplit::handle { background-color: #4a4a4a; border: 1px solid #2a2a2a; }")
        self.v_split.setSizes([650, 250])
        self.setCentralWidget(self.v_split)
        self.setAcceptDrops(True)

        self.canvas.selectionChanged.connect(self.panel.refresh)
        self.canvas.geometryChanged.connect(self.panel.update_geometry)
        self.canvas.contentChanged.connect(self._on_content_changed)
        self.canvas.requestEditText.connect(self.panel.focus_text)
        self.canvas.requestContextMenu.connect(self._show_canvas_menu)
        self.brake_btn.toggled.connect(self._on_brake_toggled)
        self.panel.addCharRequested.connect(self.add_char)
        self.panel.compensateToggled.connect(self._on_compensate_toggled)
        # 主窗口统一驱动计时
        self._sim_time = 0.0
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(20)
        self._tick_timer.timeout.connect(self._on_tick)
        self._tick_timer.start()
        # 连接信号
        self.time_control.timeReset.connect(self._on_time_reset)
        self.time_control.chk.toggled.connect(self._on_run_test_toggled)
        self._build_toolbar()

        for sig in (self.slider_vtol.slider.valueChanged,
                    self.slider_trim.slider.valueChanged,
                    self.heading_knob.dial.valueChanged,
                    self.joystick_left.area.valueChanged,
                    self.joystick_right.area.valueChanged,
                    self.landing_btn.toggled,
                    self.brake_btn.toggled):
            sig.connect(self._on_controls_changed)
        # ★ 姿态摇杆专用信号
        self.attitude_joystick.valueChanged.connect(self._on_att_joystick_changed)
        # 初始化姿态仪
        self.attitude_indicator.set_attitude(
            self._flight_data.get('PitchAngle', 0.0),
            self._flight_data.get('RollAngle', 0.0))
        self.lbl_pitch_val.setText(u"%.4f" % self._flight_data.get('PitchAngle', 0.0))
        self.lbl_roll_val.setText(u"%.4f" % self._flight_data.get('RollAngle', 0.0))
        # ★ 姿态仪积分定时器（摇杆作为变化率）
        self._att_timer = QTimer(self)
        self._att_timer.setInterval(30)
        self._att_timer.timeout.connect(self._on_att_tick)
        self._att_timer.start()
        for b in self.activate_btns:
            b.toggled.connect(self._on_controls_changed)

        self.time_control.chk.toggled.connect(self._on_run_test_toggled)
        self.canvas.run_test_active = self.time_control.chk.isChecked()

        # ★ 这些字段要在 refresh_output() 之前定义
        self._cse_defs = []
        self._var_renames = {}
        self._output_raw = u""
        self._updating_vars = False
        self._output_minimized = False
        self._saved_bottom_size = 250
        self._saved_ctrl_h = 380
        self._floating_panel = None
        self._flight_dlg = None
        self._flight_dlg_time_was_enabled = False
        # 自定义变量对话框引用已在上方初始化
        # ★ 设置保存相关
        self._settings_enabled = False
        self._settings_path = u""
        self._settings_timer = QTimer(self)
        self._settings_timer.setSingleShot(True)
        self._settings_timer.setInterval(800)
        self._settings_timer.timeout.connect(self._auto_save_settings)

        self.update_variables()
        self.canvas.eval_all(0.0)
        self.joystick_left._sync_spins_from_area()
        self.joystick_right._sync_spins_from_area()

        self._status_default = _L(
            u"滚轮缩放 | 中键/Alt+左键 平移 | {表达式} 求值",
            u"Wheel: zoom | Middle / Alt+LMB: pan | {expr}: evaluate")
        self.statusBar().showMessage(self._status_default)
        self.refresh_output()

        # ★ 初始化自定义函数列数
        QTimer.singleShot(0, self._refresh_var_layout)

        self._undo_stack = []
        self._redo_stack = []
        self._undo_pending = False
        self._restoring_undo = False
        self._undo_timer = QTimer(self)
        self._undo_timer.setSingleShot(True)
        self._undo_timer.setInterval(300)
        self._undo_timer.timeout.connect(self._commit_undo)
        QTimer.singleShot(100, self._push_undo_now)
        QShortcut(QKeySequence("Ctrl+Z"), self, self._undo)
        QShortcut(QKeySequence("Ctrl+Y"), self, self._redo)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, self._redo)
        QShortcut(QKeySequence("Ctrl+C"), self, self._copy_chars)
        QShortcut(QKeySequence("Ctrl+V"), self, self._paste_chars)
        self._clipboard_items = []
        self.canvas.contentChanged.connect(self._trigger_undo)
        self.canvas.itemsChanged.connect(self._trigger_undo)

        # ★ 让补全器知道自定义变量名
        set_global_words_provider(
            lambda: [d.get('name', u'') for d in self._custom_vars
                     if d.get('name')])

        # ★ 启动时自动恢复上次保存的设置
        QTimer.singleShot(200, self._auto_load_settings_on_startup)

    def _on_run_test_toggled(self, checked):
        # 只影响时间是否推进（由 _on_tick 检查 chk.isChecked()）
        # 显示不受影响：eval_all 始终按表达式显示
        self.canvas.run_test_active = bool(checked)

    # ---------------- 变量 ----------------
    def get_control_values(self):
        jlx = self.joystick_left.x();
        jly = self.joystick_left.y()
        yaw = jlx
        if jly >= 0:
            throttle = jly;
            brake_axis = 0.0
        else:
            throttle = 0.0;
            brake_axis = -jly
        if self.brake_btn.isChecked(): brake_axis = 1.0
        pitch = self.joystick_right.y();
        roll = self.joystick_right.x()
        return {
            "activate": [b.value() for b in self.activate_btns],
            "landing_gear": self.landing_btn.value(),
            "brake": self.brake_btn.value(),
            "vtol": self.slider_vtol.value(),
            "trim": self.slider_trim.value(),
            "heading": self.heading_knob.value(),
            "throttle": throttle, "brake_axis": brake_axis,
            "yaw": yaw, "pitch": pitch, "roll": roll,
        }

    def update_variables(self):
        vals = self.get_control_values()
        v = {
            'Throttle': vals['throttle'], 'Yaw': vals['yaw'],
            'Brake': vals['brake_axis'], 'Pitch': vals['pitch'],
            'Roll': vals['roll'], 'Heading': vals['heading'],
            'VTOL': vals['vtol'], 'Trim': vals['trim'],
            'LandingGear': vals['landing_gear'],
        }
        for i, a in enumerate(vals['activate']):
            v['Activate%d' % (i + 1)] = a
        v.update(self._flight_data)
        v['Time'] = self.time_control.value()
        v['pi'] = _math.pi
        v['e'] = _math.e
        # ★ 玩家自定义变量
        try:
            for d in self._custom_vars:
                n = d.get('name', u"")
                if n:
                    v[n] = float(d.get('value', 0.0))
        except Exception:
            pass
        self.canvas.variables = v

    def _on_att_joystick_changed(self):
        """摇杆现在是变化率控制：只触发 UI 更新，角度由 _on_att_tick 积分。"""
        pass

    def _on_att_tick(self):
        """姿态摇杆 → 角度变化率积分；松手（回中）后不再变化。"""
        x = self.attitude_joystick.x()
        y = self.attitude_joystick.y()
        if abs(x) < 1e-3 and abs(y) < 1e-3:
            return
        # ★ 垂直反转：默认（按钮未按下）就反转
        if not self.btn_att_invert.isChecked():
            y = -y
        dt = 0.03
        rate = 60.0  # 每秒变化 60 度（满舵时）
        roll = self._flight_data.get('RollAngle', 0.0) + x * rate * dt
        pitch = self._flight_data.get('PitchAngle', 0.0) + y * rate * dt
        roll = max(-90.0, min(90.0, roll))
        pitch = max(-90.0, min(90.0, pitch))
        self._flight_data['RollAngle'] = roll
        self._flight_data['PitchAngle'] = pitch
        self.attitude_indicator.set_attitude(pitch, roll)
        try:
            self.lbl_pitch_val.setText(u"%.4f" % pitch)
            self.lbl_roll_val.setText(u"%.4f" % roll)
        except Exception:
            pass
        self.update_variables()
        self.canvas.eval_all(0.0)
        self.canvas.update()
        self.panel.refresh_preview()
        if self._flight_dlg is not None and self._flight_dlg.isVisible():
            self._flight_dlg.set_one('PitchAngle', pitch)
            self._flight_dlg.set_one('RollAngle', roll)

    def _reset_attitude_angles(self):
        """姿态摇杆回位按钮：角度归 0，仪表和数值框同步归零。
        （摇杆本身的回中由 VirtualJoystick.reset 自动处理）"""
        self._flight_data['PitchAngle'] = 0.0
        self._flight_data['RollAngle'] = 0.0
        self.attitude_indicator.set_attitude(0.0, 0.0)
        try:
            self.lbl_pitch_val.setText(u"0.0000")
            self.lbl_roll_val.setText(u"0.0000")
        except Exception:
            pass
        self.update_variables()
        self.canvas.eval_all(0.0)
        self.canvas.update()
        self.panel.refresh_preview()
        if self._flight_dlg is not None and self._flight_dlg.isVisible():
            self._flight_dlg.set_one('PitchAngle', 0.0)
            self._flight_dlg.set_one('RollAngle', 0.0)

    def _on_controls_changed(self, *args):
        self.update_variables()
        self.canvas.eval_all(0.0);
        self.canvas.update()
        self.panel.refresh_preview()
        if self._flight_dlg is not None and self._flight_dlg.isVisible():
            self._flight_dlg.set_values(self._collect_all_values())
        if self._floating_panel is not None:
            try:
                aoa = self._flight_data.get('AngleOfAttack', 0.0)
                self._floating_panel.aoa_knob.set_value(aoa)
                self._floating_panel.speed_knob.set_values(self._flight_data)
            except Exception:
                pass

    def _on_tick(self):
        if not self.time_control.chk.isChecked():
            return
        speed = self.time_control.spin_speed.value()
        dt = 0.02 * speed
        self._sim_time += dt
        if self._sim_time < 0:
            self._sim_time = 0.0
        self.time_control._time = self._sim_time
        self.time_control.spin_time.blockSignals(True)
        self.time_control.spin_time.setValue(self._sim_time)
        self.time_control.spin_time.blockSignals(False)
        self.canvas.current_time = self._sim_time
        self.update_variables()
        self.canvas.eval_all(dt)
        self.canvas.update()
        self.panel.refresh_preview()

    def _on_time_reset(self):
        # 1) 关闭勾选（阻塞信号避免触发 toggled 分支）
        self.time_control.chk.blockSignals(True)
        self.time_control.chk.setChecked(False)
        self.time_control.chk.blockSignals(False)
        self.canvas.run_test_active = False

        # 2) 清空所有元素状态（sum/rate/smooth/PID 累计值 + 显示缓存）
        for it in self.canvas.items:
            it._expr_state.data.clear()
            it._disp_size = None
            it._disp_x = None
            it._disp_y = None
            it._disp_rot = None

        # 3) 时间归 0
        self._sim_time = 0.0
        self.canvas.current_time = 0.0
        self.time_control._time = 0.0
        self.time_control.spin_time.blockSignals(True)
        self.time_control.spin_time.setValue(0.0)
        self.time_control.spin_time.blockSignals(False)

        # 4) 刷新
        self.update_variables()
        self.canvas.eval_all(0.0)
        self.canvas.update()
        self.panel.refresh_preview()

    def _on_brake_toggled(self, checked):
        if checked:
            self.joystick_left.set_forced_value('Brk', 100)
        else:
            self.joystick_left.set_forced_value('Brk', None)

    def _edit_bind_props(self, obj):
        """右键 → 修改吸附属性：打开控制方式配置对话框"""
        bind_to = getattr(obj, 'bind_to', u'')
        if not bind_to:
            return
        byname = self.canvas._all_objects_by_name()
        parent = byname.get(bind_to)
        if parent is None:
            QMessageBox.warning(
                self, _T('hint'),
                _L(u"父对象 [%s] 未找到", u"Parent [%s] not found")
                % bind_to)
            return
        dlg = BindControlDialog(obj, parent, self.canvas, self)
        if dlg.exec_() == QDialog.Accepted:
            dx_expr, dy_expr, ang_expr = dlg.values()
            obj.bind_dx_expr = dx_expr
            obj.bind_dy_expr = dy_expr
            obj.bind_angle_expr = ang_expr
            self.canvas.eval_all(0.0)
            self.canvas.update()
            self.canvas.contentChanged.emit()

    def _debug_bind(self, obj):
        info = self.canvas.debug_bind_info(obj)
        print(u"===== bind debug =====")
        print(info)
        print(u"======================")
        QMessageBox.information(self, u"绑定诊断", info)

    def _quick_slide_line(self, obj):
        """一键：吸附到第一条辅助线并写入滑动公式，不弹对话框。"""
        if not self.canvas.helper_lines:
            QMessageBox.information(
                self, _T('hint'),
                _L(u"画布上没有辅助线", u"No helper line on canvas"))
            return
        line = self.canvas.helper_lines[0]
        if not (getattr(line, 'name', u'') or u''):
            line.name = self.canvas._next_helper_name('L')
        line_name = line.name

        px, py = self.canvas._obj_pos(line)
        parent_rot0 = self.canvas._obj_rot(line)
        a0 = math.radians(parent_rot0)
        ca, sa = math.cos(a0), math.sin(a0)
        ox, oy = self.canvas._obj_pos(obj)
        wx = ox - px;
        wy = oy - py
        dx = wx * ca - wy * sa
        dy = wx * sa + wy * ca
        obj_rot0 = self.canvas._obj_rot(obj)

        obj.bind_to = line_name
        obj.bind_dx = dx
        obj.bind_dy = dy
        obj.bind_angle = obj_rot0 - parent_rot0
        # ★ 吸附的字符自动开启偏移补偿
        if isinstance(obj, RichItem):
            obj.compensate_offset = True

        ctrl = u"Activate1"
        t_norm = u"clamp(((%s)-(0))/(1),0,1)" % ctrl
        half_norm = u"((%s)-0.5)" % t_norm
        L_expr = (u"sqrt(({%s_X2}-{%s_X1})*({%s_X2}-{%s_X1})"
                  u"+({%s_Y2}-{%s_Y1})*({%s_Y2}-{%s_Y1}))"
                  % (line_name, line_name, line_name, line_name,
                     line_name, line_name, line_name, line_name))
        obj.bind_dx_expr = u"%s*(%s)" % (half_norm, L_expr)
        obj.bind_dy_expr = u"0"
        obj.bind_angle_expr = u""

        # 保存对话框元信息，下次右键"修改吸附属性"能正确恢复
        obj._bind_dialog_mode = 'slide'
        obj._bind_dialog_ctrl = ctrl
        obj._bind_dialog_t0 = 0.0
        obj._bind_dialog_t1 = 1.0
        obj._bind_dialog_tangent = False
        obj._bind_dialog_start_angle = 0.0
        obj._bind_dialog_obj_offset = 0.0

        self.canvas.eval_all(0.0)
        self.canvas.update()
        self.canvas.contentChanged.emit()
        self.refresh_output()
        QMessageBox.information(
            self, _L(u"完成", u"Done"),
            _L(u"已将 [%s] 吸附到 [%s] 并生成滑动公式。\n"
               u"点/松 Activate1 按钮即可看到字符沿辅助线滑动。",
               u"Bound [%s] to [%s] with slide formula.\n"
               u"Toggle Activate1 to see it slide along the line.")
            % (getattr(obj, 'name', u'?'), line_name))

    def _quick_orbit_circle(self, obj):
        """一键：吸附到第一个辅助圆并写入绕圆公式。"""
        if not self.canvas.helper_circles:
            QMessageBox.information(
                self, _T('hint'),
                _L(u"画布上没有辅助圆", u"No helper circle on canvas"))
            return
        circ = self.canvas.helper_circles[0]
        if not (getattr(circ, 'name', u'') or u''):
            circ.name = self.canvas._next_helper_name('C')
        cname = circ.name

        px, py = self.canvas._obj_pos(circ)
        parent_rot0 = self.canvas._obj_rot(circ)
        a0 = math.radians(parent_rot0)
        ca, sa = math.cos(a0), math.sin(a0)
        ox, oy = self.canvas._obj_pos(obj)
        wx = ox - px;
        wy = oy - py
        dx = wx * ca - wy * sa
        dy = wx * sa + wy * ca
        obj_rot0 = self.canvas._obj_rot(obj)

        obj.bind_to = cname
        obj.bind_dx = dx
        obj.bind_dy = dy
        obj.bind_angle = obj_rot0 - parent_rot0
        # ★ 吸附的字符自动开启偏移补偿
        if isinstance(obj, RichItem):
            obj.compensate_offset = True

        R = circ.dr()
        ctrl = u"Activate1"
        t_norm = u"clamp(((%s)-(0))/(1),0,1)" % ctrl
        theta = u"(%s)*360" % t_norm
        # ★ 用辅助引用 {Cn_R}，而不是硬编码 R
        if cname:
            R_expr = u"{%s_R}" % cname
        else:
            R_expr = _fmt(R)
        obj.bind_dx_expr = u"(-%s)*sin(%s)" % (R_expr, theta)
        obj.bind_dy_expr = u"(-%s)*cos(%s)" % (R_expr, theta)
        obj.bind_angle_expr = u"0"

        obj._bind_dialog_mode = 'orbit'
        obj._bind_dialog_ctrl = ctrl
        obj._bind_dialog_t0 = 0.0
        obj._bind_dialog_t1 = 1.0
        obj._bind_dialog_tangent = False
        obj._bind_dialog_start_angle = 0.0
        obj._bind_dialog_obj_offset = 0.0

        self.canvas.eval_all(0.0)
        self.canvas.update()
        self.canvas.contentChanged.emit()
        self.refresh_output()
        QMessageBox.information(
            self, _L(u"完成", u"Done"),
            _L(u"已将 [%s] 吸附到 [%s] 并生成绕圆公式。\n"
               u"点/松 Activate1 按钮即可看到字符绕圆运动。",
               u"Bound [%s] to [%s] with orbit formula.\n"
               u"Toggle Activate1 to see it orbit.")
            % (getattr(obj, 'name', u'?'), cname))

    def _quick_unbind(self, obj):
        """右键 → 解除吸附：把当前位置写回静态，避免跳回"""
        if isinstance(obj, RichItem):
            if obj._disp_x is not None: obj.x = obj._disp_x
            if obj._disp_y is not None: obj.y = obj._disp_y
        elif isinstance(obj, HelperPoint):
            if obj._disp_x is not None: obj.x = obj._disp_x
            if obj._disp_y is not None: obj.y = obj._disp_y
        elif isinstance(obj, HelperLine):
            if obj._disp_x1 is not None:
                obj.x1 = obj._disp_x1;
                obj.y1 = obj._disp_y1
            if obj._disp_x2 is not None:
                obj.x2 = obj._disp_x2;
                obj.y2 = obj._disp_y2
        obj.bind_to = u""
        obj.bind_dx_expr = u""
        obj.bind_dy_expr = u""
        obj.bind_angle_expr = u""
        self.canvas.eval_all(0.0)
        self.canvas.update()
        self.canvas.contentChanged.emit()

    def _start_bind_for_object(self, hit_obj=None):
        """右键 → 吸附到…：
        - 若命中的对象属于当前多选 → 用整个多选作为子级
        - 否则只用命中对象作为子级
        然后进入拾取父级模式。
        """
        if hit_obj is None:
            return
        if (isinstance(hit_obj, RichItem)
                and hit_obj in self.canvas.selected):
            children = list(self.canvas.selected)
        elif hit_obj in self.canvas.selected_helpers:
            children = list(self.canvas.selected_helpers)
        else:
            children = [hit_obj]
        try:
            self.panel.start_bind_with_children(children)
        except Exception:
            pass

    def _set_helper_tool_from_menu(self, tool):
        """通过右键菜单切换辅助线工具（复用面板按钮，保证互斥状态同步）"""
        try:
            btn_map = {
                'point': self.panel.btn_tool_point,
                'line': self.panel.btn_tool_line,
                'circle': self.panel.btn_tool_circle,
            }
            btn = btn_map.get(tool)
            if btn is not None:
                btn.setChecked(True)
        except Exception:
            pass

    def _show_canvas_menu(self, global_pos, wx, wy):
        """右键菜单：空区域弹出，点/线/圆直接在右键位置放置"""
        m = QMenu(self)

        # ★ 正在拾取父级：只显示"取消吸附"
        if self.canvas.bind_pick_mode:
            n = len(getattr(self.panel, '_bind_pick_children', []))
            act_cancel = m.addAction(
                _L(u"✂  取消吸附（已选 %d 个子对象）",
                   u"✂  Cancel binding (%d children selected)") % n)
            act_cancel.triggered.connect(self.panel.cancel_bind)
            m.exec_(global_pos)
            return

        # ★ 如果命中了对象，顶部显示对象专属项
        hit_obj = getattr(self.canvas, '_context_hit_obj', None)
        if hit_obj is not None:
            obj_name = (getattr(hit_obj, 'name', u'')
                        or _L(u'(未命名)', u'(unnamed)'))
            kind = (_L(u"字符", u"Char") if isinstance(hit_obj, RichItem)
                    else _L(u"辅助点", u"Helper Point")
                    if isinstance(hit_obj, HelperPoint)
                    else _L(u"辅助线", u"Helper Line")
                    if isinstance(hit_obj, HelperLine)
                    else _L(u"辅助圆", u"Helper Circle"))
            title_act = m.addAction(u"■ %s  [%s]" % (kind, obj_name))
            title_act.setEnabled(False)

            bind_to = getattr(hit_obj, 'bind_to', u'')
            if bind_to:
                act_edit = m.addAction(
                    _L(u"⚙  修改吸附属性…", u"⚙  Edit Binding…"))
                act_edit.triggered.connect(
                    lambda c=False, o=hit_obj: self._edit_bind_props(o))
                act_unbind = m.addAction(
                    _L(u"✂  解除吸附", u"✂  Unbind"))
                act_unbind.triggered.connect(
                    lambda c=False, o=hit_obj: self._quick_unbind(o))
            else:
                n_sel = (len(self.canvas.selected)
                         + len(self.canvas.selected_helpers))
                if n_sel > 1 and (hit_obj in self.canvas.selected
                                  or hit_obj in self.canvas.selected_helpers):
                    label = _L(u"🔗  吸附到…（%d 个对象作为子级）",
                               u"🔗  Bind to… (%d objects as children)") % n_sel
                else:
                    label = _L(u"🔗  吸附到…", u"🔗  Bind to…")
                act_bind = m.addAction(label)
                act_bind.triggered.connect(
                    lambda c=False, o=hit_obj: self._start_bind_for_object(o))
            m.addSeparator()

        # 1. 添加字符（在右键位置添加）
        m.addAction(_T('add_char'),
                    lambda: self.add_char_at(wx, wy))

        # 2. 插入符号（二级菜单，在右键位置添加）
        sym_menu = m.addMenu(_T('insert_sym'))
        for label, text, rot in SYMBOL_MENU_ITEMS:
            sym_menu.addAction(
                label,
                lambda ch=text, r=rot: self.add_symbol_at(ch, r, wx, wy))

        # 3. 辅助线（二级菜单，直接在右键位置创建）
        helper_menu = m.addMenu(_T('helpers_menu'))
        helper_menu.addAction(
            _L(u"● 点", u"● Point"),
            lambda: self.canvas.create_helper_at('point', wx, wy))
        helper_menu.addAction(
            _L(u"／ 线", u"／ Line"),
            lambda: self.canvas.create_helper_at('line', wx, wy))
        helper_menu.addAction(
            _L(u"○ 圆", u"○ Circle"),
            lambda: self.canvas.create_helper_at('circle', wx, wy))

        m.addSeparator()

        # 4. 隐藏/显示控制面板
        act_ctrl = m.addAction(_T('menu_ctrl'))
        act_ctrl.setCheckable(True)
        act_ctrl.setChecked(self.act_ctrl_toggle.isChecked())
        act_ctrl.setEnabled(self._floating_panel is None)
        act_ctrl.toggled.connect(self.act_ctrl_toggle.setChecked)

        m.addSeparator()

        # 5. 显示网格
        act_grid = m.addAction(_T('show_grid'))
        act_grid.setCheckable(True)
        act_grid.setChecked(self.canvas.show_grid)
        act_grid.toggled.connect(
            lambda v: (setattr(self.canvas, "show_grid", bool(v)),
                       self.canvas.update()))

        # 6. 显示方框
        act_bounds = m.addAction(_T('show_bounds'))
        act_bounds.setCheckable(True)
        act_bounds.setChecked(self.canvas.show_bounds)
        act_bounds.toggled.connect(
            lambda v: (setattr(self.canvas, "show_bounds", bool(v)),
                       self.canvas.update()))

        # 7. 显示标尺
        act_ruler = m.addAction(_T('show_ruler'))
        act_ruler.setCheckable(True)
        act_ruler.setChecked(self.canvas.show_ruler)
        act_ruler.toggled.connect(
            lambda v: (setattr(self.canvas, "show_ruler", bool(v)),
                       self.canvas.update()))

        m.exec_(global_pos)

    # ---------------- 撤销/重做 ----------------
    def _snapshot(self):
        try:
            pts = self.canvas.helper_points
            lns = self.canvas.helper_lines
            cirs = self.canvas.helper_circles
            hlist = pts + lns + cirs
            hidx = {id(h): i for i, h in enumerate(hlist)}
            data = {
                "tree": self._node_to_dict(self.canvas.root, hidx),
                "helpers": _encode_helpers(pts, lns, cirs),
            }
            return json.dumps(data, ensure_ascii=False)
        except Exception:
            return None

    def _trigger_undo(self):
        if self._restoring_undo: return
        self._undo_pending = True
        self._undo_timer.start()

    def _commit_undo(self):
        if not self._undo_pending: return
        self._undo_pending = False
        if self._restoring_undo: return
        snap = self._snapshot()
        if snap is None: return
        if self._undo_stack and self._undo_stack[-1] == snap: return
        self._undo_stack.append(snap)
        if len(self._undo_stack) > 50: self._undo_stack.pop(0)
        self._redo_stack.clear()

    def _push_undo_now(self):
        if self._restoring_undo: return
        snap = self._snapshot()
        if snap is None: return
        if self._undo_stack and self._undo_stack[-1] == snap: return
        self._undo_stack.append(snap)
        if len(self._undo_stack) > 50: self._undo_stack.pop(0)
        self._redo_stack.clear()

    def _apply_snapshot(self, snap):
        if snap is None: return
        self._restoring_undo = True
        try:
            d = json.loads(snap)
            tree_data = d.get("tree") if "tree" in d else d
            hlist = []
            if "helpers" in d:
                pts, lns, cirs = _decode_helpers(d["helpers"])
                hlist = pts + lns + cirs
            nr = self._dict_to_node(tree_data, hlist)
            nr.parent = None;
            nr.folder = True
            self.canvas.root = nr
            self.canvas._resync_helper_lists()
            self._sync_helper_name_seq()
            self.canvas.selected = []
            self.canvas.selected_helpers = []
            self.canvas.selectionChanged.emit()
            self.canvas.eval_all(0.0);
            self.canvas.update()
            self.charlist.rebuild();
            self.refresh_output()
        except Exception:
            pass
        finally:
            self._restoring_undo = False

    def _undo(self):
        if not self._undo_stack: return
        cur = self._snapshot()
        if self._undo_pending:
            self._undo_timer.stop();
            self._undo_pending = False
            if cur is not None and (not self._undo_stack
                                    or self._undo_stack[-1] != cur):
                self._undo_stack.append(cur)
        if len(self._undo_stack) < 2: return
        self._redo_stack.append(self._undo_stack.pop())
        self._apply_snapshot(self._undo_stack[-1])

    def _redo(self):
        if not self._redo_stack: return
        snap = self._redo_stack.pop()
        self._undo_stack.append(snap)
        self._apply_snapshot(snap)

    def _copy_chars(self):
        """Ctrl+C：复制选中字符到内部剪贴板"""
        sel = list(self.canvas.selected)
        if not sel:
            return
        try:
            self._clipboard_items = [it.to_dict() for it in sel]
            self.statusBar().showMessage(
                _L(u"已复制 %d 个对象", u"Copied %d object(s)")
                % len(sel), 2000)
        except Exception:
            self._clipboard_items = []

    def _paste_chars(self):
        """Ctrl+V：在鼠标位置粘贴；
        若开了网格吸附，则吸附到最近网格。
        """
        if not self._clipboard_items:
            return
        # 鼠标位置 → 画布局部 → 世界坐标
        try:
            gp = QCursor.pos()
            lp = self.canvas.mapFromGlobal(gp)
            wpos = self.canvas.screen_to_world(QPointF(lp))
            mx, my = wpos.x(), wpos.y()
        except Exception:
            mx, my = 0.0, 0.0
        if self.canvas.snap_enabled:
            try:
                mx = self.canvas._snap_world(mx)
                my = self.canvas._snap_world(my)
            except Exception:
                pass
        # 复制内容的外接框中心
        try:
            xs = [float(d.get("x", 0.0)) for d in self._clipboard_items]
            ys = [float(d.get("y", 0.0)) for d in self._clipboard_items]
            cx = (min(xs) + max(xs)) / 2.0
            cy = (min(ys) + max(ys)) / 2.0
        except Exception:
            cx, cy = 0.0, 0.0
        new_items = []
        for d in self._clipboard_items:
            try:
                it = RichItem.from_dict(d)
                it.x = mx + (it.x - cx)
                it.y = my + (it.y - cy)
                it.name = self.canvas._next_char_name()
                self.canvas.append_item(it)
                new_items.append(it)
            except Exception:
                continue
        if not new_items:
            return
        self.canvas.selected = new_items
        self.canvas.selected_helpers = []
        self.canvas.selectionChanged.emit()
        self.canvas.itemsChanged.emit()
        self.canvas.eval_all(0.0)
        self.canvas.update()
        self.canvas.contentChanged.emit()
        self.statusBar().showMessage(
            _L(u"已粘贴 %d 个对象", u"Pasted %d object(s)")
            % len(new_items), 2000)

    # ---------------- 输出最小化 ----------------
    def _toggle_output_min(self):
        self._output_minimized = not self._output_minimized
        if self._output_minimized:
            self.output_edit.setVisible(False)
            self._left_top_spacer.setVisible(True)
            self._left_widget.setAttribute(Qt.WA_StyledBackground, True)
            self._left_widget.setStyleSheet(
                "#leftOutput { background-color: #242424; border: none; }"
                "#leftOutput QLabel { color: #dddddd; background: transparent; border: none; }"
                "#leftOutput QCheckBox { color: #dddddd; background: transparent; }")
            self.v_split.setStyleSheet(
                "QSplitter#mainVSplit::handle { background-color: #242424; border: none;}")
            if self._floating_panel is None:
                self._ctrl_widget.setParent(None)
                self._right_split.addWidget(self._ctrl_widget)
                self._ctrl_widget.setMinimumHeight(self._saved_ctrl_h)
                self._ctrl_widget.setMaximumHeight(self._saved_ctrl_h)
                total_h = sum(self._right_split.sizes())
                above = max(160, total_h - self._saved_ctrl_h)
                self._right_split.setSizes([int(above * 0.75),
                                            int(above * 0.25),
                                            self._saved_ctrl_h])
            sizes = self.v_split.sizes();
            total = sum(sizes)
            if len(sizes) > 1: self._saved_bottom_size = sizes[1]
            self.v_split.setSizes([total - 46, 46])
            try:
                self.v_split.splitterMoved.disconnect(self._on_vsplit_moved_min)
            except Exception:
                pass
            self.v_split.splitterMoved.connect(self._on_vsplit_moved_min)
            self.btn_min.setText(_T('expand'))
        else:
            try:
                self.v_split.splitterMoved.disconnect(self._on_vsplit_moved_min)
            except Exception:
                pass
            if self._floating_panel is None:
                self._ctrl_widget.setMinimumHeight(0)
                self._ctrl_widget.setMaximumHeight(16777215)
                self._ctrl_widget.setParent(None)
                self._bottom_split.insertWidget(1, self._ctrl_widget)
                self._bottom_split.setSizes([840, 520])
            self._right_split.setSizes([700, 190])
            self.output_edit.setVisible(True)
            self._left_top_spacer.setVisible(False)
            self._left_widget.setStyleSheet("")
            self._left_widget.setAttribute(Qt.WA_StyledBackground, False)
            self.v_split.setStyleSheet(
                "QSplitter#mainVSplit::handle { background-color: #4a4a4a; border: 1px solid #2a2a2a; }")
            self.btn_min.setText(_T('minimize'))
            sizes = self.v_split.sizes();
            total = sum(sizes)
            restore = max(160, self._saved_bottom_size)
            self.v_split.setSizes([max(400, total - restore), restore])
        # ★ 输出最小化状态切换后，重新计算自定义变量表的列组数
        QTimer.singleShot(0, self._refresh_var_layout)
        # ★ 顺便刷一次标题栏（含字节数）
        try:
            self._update_output_title_bytes()
        except Exception:
            pass

    def _on_vsplit_moved_min(self, pos, index):
        if not self._output_minimized: return
        sizes = self.v_split.sizes()
        if len(sizes) < 2: return
        total = sum(sizes)
        self.v_split.blockSignals(True)
        self.v_split.setSizes([total - 46, 46])
        self.v_split.blockSignals(False)

    def _toggle_ctrl_visible(self, checked):
        if self._floating_panel is not None:
            self.act_ctrl_toggle.setChecked(True);
            return
        self._ctrl_minimized = not checked
        self._ctrl_widget.setVisible(checked)
        if not checked:
            if self._ctrl_widget.parent() is self._bottom_split:
                self._bottom_split.setSizes([2000, 0])
            elif self._ctrl_widget.parent() is self._right_split:
                cur = self._right_split.sizes()
                if len(cur) >= 3: self._right_split.setSizes([cur[0], cur[1], 0])
        else:
            if self._ctrl_widget.parent() is self._bottom_split:
                self._bottom_split.setSizes([840, 520])
            elif self._ctrl_widget.parent() is self._right_split:
                self._right_split.setSizes([250, 80, self._saved_ctrl_h])
        # ★ 同步按钮文案
        try:
            self.btn_ctrl_min.setText(
                _T('expand') if self._ctrl_minimized else _T('minimize'))
        except Exception:
            pass
        # ★ 同步“显示控制面板”按钮位置
        try:
            self._update_show_ctrl_btn()
        except Exception:
            pass
        # ★ 触发列组重排（最小化→3列，恢复→按宽度）
        QTimer.singleShot(0, self._refresh_var_layout)

    def _toggle_ctrl_min(self):
        """控制面板最小化/恢复：复用工具栏的 🎛 控制面板 开关，
        保证按钮与菜单状态始终同步。"""
        if self._floating_panel is not None:
            return  # 浮动模式下无意义
        self.act_ctrl_toggle.setChecked(not self.act_ctrl_toggle.isChecked())

    def _update_show_ctrl_btn(self):
        """根据当前状态，决定"显示控制面板"按钮出现在哪：

        · 控制面板未最小化            → 两个都隐藏
        · 浮动模式（独立窗口）        → 两个都隐藏
        · 最小化 + 自定义函数面板可见  → 显示在自定义函数表头
        · 最小化 + 自定义函数面板隐藏  → 显示在输出面板表头
        """
        try:
            b_in = getattr(self, 'btn_show_ctrl', None)
            b_out = getattr(self, 'btn_show_ctrl_out', None)
            if b_in is None or b_out is None:
                return
            # 浮动模式下无意义
            if self._floating_panel is not None:
                b_in.setVisible(False)
                b_out.setVisible(False)
                return
            # 未最小化 → 都隐藏
            if not self._ctrl_minimized:
                b_in.setVisible(False)
                b_out.setVisible(False)
                return
            # 最小化中：看自定义函数面板是否可见
            panel_visible = False
            try:
                panel_visible = bool(self._var_wrap.isVisible())
            except Exception:
                pass
            if panel_visible:
                b_in.setVisible(True)
                b_out.setVisible(False)
            else:
                b_in.setVisible(False)
                b_out.setVisible(True)
        except Exception:
            pass

    def _show_ctrl_from_var(self):
        """自定义函数面板上方的“显示控制面板”按钮"""
        if self._floating_panel is not None:
            try:
                self._floating_panel.raise_()
                self._floating_panel.activateWindow()
            except Exception:
                pass
            return
        if self._ctrl_minimized:
            self.act_ctrl_toggle.setChecked(True)

    def _toggle_float_panel(self):
        if self._floating_panel is None:
            self._do_float_panel()
        else:
            self._do_dock_panel()

    def _do_float_panel(self):
        self._ctrl_widget.setParent(None)
        self._floating_panel = FloatingControlPanel(self)
        self._floating_panel.dockRequested.connect(self._do_dock_panel)
        self._floating_panel.showFlightDataRequested.connect(self.show_flight_data)
        self._floating_panel.showCustomVarsRequested.connect(self.show_custom_vars)
        self._floating_panel.showTargetCtrlRequested.connect(self.show_target_control)
        self._floating_panel.aoa_knob.valueChanged.connect(self._on_aoa_changed)
        self._floating_panel.speed_knob.speedChanged.connect(self._on_speed_changed)
        self._floating_panel.take_widget(self._ctrl_widget)
        try:
            cl = self._ctrl_center_layout
            insert_at = cl.count() - 1  # stretch 之前

            # 左列：AoA 在上、Speed 在下
            left_col = QWidget()
            left_lay = QVBoxLayout(left_col)
            left_lay.setContentsMargins(0, 0, 0, 0)
            left_lay.setSpacing(4)
            left_lay.addWidget(self._floating_panel.aoa_knob)
            left_lay.addWidget(self._floating_panel.speed_knob)
            left_lay.addStretch(1)

            # 水平行：[AoA/Speed 列] [姿态仪容器]
            row = QWidget()
            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(0, 0, 0, 0)
            row_lay.setSpacing(16)
            row_lay.addWidget(left_col, 0)
            row_lay.addWidget(self._att_container, 0)
            row_lay.addStretch(1)

            cl.insertWidget(insert_at, row)
            self._att_row = row
            self._att_container.setVisible(True)
        except Exception:
            pass
        try:
            aoa = self._flight_data.get('AngleOfAttack', 0.0)
            self._floating_panel.aoa_knob.set_value(aoa)
            self._floating_panel.speed_knob.set_values(self._flight_data)
        except Exception:
            pass
        self._floating_panel.show()
        try:
            self.btn_float_panel.setVisible(False)
        except Exception:
            pass
        try:
            self.btn_ctrl_min.setVisible(False)
        except Exception:
            pass
        # ★ 浮出时隐藏 ctrl 内嵌的三个按钮（避免和浮动面板顶部重复）
        try:
            self.btn_flight_data_main.setVisible(False)
        except Exception:
            pass
        try:
            self.btn_custom_vars_main.setVisible(False)
        except Exception:
            pass
        try:
            self.btn_target_ctrl_main.setVisible(False)
        except Exception:
            pass
        try:
            self.act_ctrl_toggle.setEnabled(False)
        except Exception:
            pass
        # ★ 浮出后控制面板可见，重置最小化状态 + 隐藏恢复按钮 + 强制 3 列
        self._ctrl_minimized = False
        try:
            self._update_show_ctrl_btn()
        except Exception:
            pass
        QTimer.singleShot(0, self._refresh_var_layout)
        self._apply_language()

    def _do_dock_panel(self):
        if self._floating_panel is None: return
        # ★ 拆除水平行，把姿态仪容器收回（不加入任何布局）
        try:
            if self._att_row is not None:
                self._ctrl_center_layout.removeWidget(self._att_row)
                self._att_container.setParent(None)
                self._att_container.setVisible(False)
                self._att_row.deleteLater()
                self._att_row = None
        except Exception:
            pass
        try:
            self._floating_panel.aoa_knob.deleteLater()
            self._floating_panel.speed_knob.deleteLater()
        except Exception:
            pass
        w = self._floating_panel.release_widget()
        try:
            self._floating_panel.dockRequested.disconnect(self._do_dock_panel)
        except Exception:
            pass
        try:
            self._floating_panel.showFlightDataRequested.disconnect(self.show_flight_data)
        except Exception:
            pass
        try:
            self._floating_panel.showCustomVarsRequested.disconnect(self.show_custom_vars)
        except Exception:
            pass
        try:
            self._floating_panel.showTargetCtrlRequested.disconnect(self.show_target_control)
        except Exception:
            pass
        try:
            self._floating_panel.aoa_knob.valueChanged.disconnect(self._on_aoa_changed)
        except Exception:
            pass
        try:
            self._floating_panel.speed_knob.speedChanged.disconnect(self._on_speed_changed)
        except Exception:
            pass
        self._floating_panel.close()
        self._floating_panel.deleteLater()
        self._floating_panel = None
        if w is not None:
            if self._output_minimized:
                self._right_split.addWidget(w)
                w.setMinimumHeight(self._saved_ctrl_h)
                w.setMaximumHeight(self._saved_ctrl_h)
                total_h = sum(self._right_split.sizes())
                above = max(160, total_h - self._saved_ctrl_h)
                self._right_split.setSizes([int(above * 0.75),
                                            int(above * 0.25),
                                            self._saved_ctrl_h])
            else:
                w.setMinimumHeight(0);
                w.setMaximumHeight(16777215)
                self._bottom_split.insertWidget(1, w)
                self._bottom_split.setSizes([840, 520])
        try:
            self.btn_float_panel.setVisible(True)
        except Exception:
            pass
        try:
            self.btn_ctrl_min.setVisible(True)
        except Exception:
            pass
        # ★ 停靠后恢复 ctrl 内嵌的三个按钮
        try:
            self.btn_flight_data_main.setVisible(True)
        except Exception:
            pass
        try:
            self.btn_custom_vars_main.setVisible(True)
        except Exception:
            pass
        try:
            self.btn_target_ctrl_main.setVisible(True)
        except Exception:
            pass
        try:
            self.act_ctrl_toggle.setEnabled(True)
        except Exception:
            pass
        # ★ 停靠后控制面板可见，重置最小化状态 + 隐藏恢复按钮 + 按宽度重排
        self._ctrl_minimized = False
        try:
            self._update_show_ctrl_btn()
        except Exception:
            pass
        QTimer.singleShot(0, self._refresh_var_layout)
        self._apply_language()

    def _on_aoa_changed(self, v):
        self._flight_data['AngleOfAttack'] = float(v)
        self.update_variables()
        self.canvas.eval_all(0.0);
        self.canvas.update()
        if self._flight_dlg is not None and self._flight_dlg.isVisible():
            self._flight_dlg.set_one('AngleOfAttack', v)

    def _on_speed_changed(self, key, v):
        if key in self._flight_data:
            self._flight_data[key] = float(v)
            self.update_variables()
            self.canvas.eval_all(0.0);
            self.canvas.update()
            if self._flight_dlg is not None and self._flight_dlg.isVisible():
                self._flight_dlg.set_one(key, v)

    # ---------------- 自定义变量对话框 ----------------
    def _reserved_var_names(self):
        names = set(CONTROL_VARS) | set(FLIGHT_VARS) | {'Time', 'pi', 'e'}
        names |= set(EXPR_FUNCS.keys())
        return names

    def show_custom_vars(self):
        """打开玩家“自定义变量”编辑窗口（CustomVarsDialog）。

        控制面板上的“自定义变量”按钮、“更多 → 📋 自定义变量”菜单
        都走这里。
        """
        # 已打开 → 前置
        if (self._custom_vars_dlg is not None
                and self._custom_vars_dlg.isVisible()):
            try:
                self._custom_vars_dlg.raise_()
                self._custom_vars_dlg.activateWindow()
            except Exception:
                pass
            return
        try:
            # ★ parent 传 None：作为独立顶层窗口，不永远压在主窗口上
            dlg = CustomVarsDialog(self._custom_vars,
                                   self._reserved_var_names, None)
            dlg.varsChanged.connect(self._on_custom_vars_changed)
            dlg.closed.connect(self._on_custom_vars_closed)
            dlg.show()
            self._custom_vars_dlg = dlg
        except Exception as ex:
            import traceback
            traceback.print_exc()
            QMessageBox.warning(
                self, _T('hint'),
                u"自定义变量窗口打开失败：%r" % (ex,))

    def show_target_control(self):
        """打开目标控制窗口（占位实现，后续接 3D 场景）。"""
        if (self._target_dlg is not None
                and self._target_dlg.isVisible()):
            try:
                self._target_dlg.raise_()
                self._target_dlg.activateWindow()
            except Exception:
                pass
            return
        try:
            dlg = TargetControlDialog(self._flight_data, None)
            # ★ 恢复上次保存的 3D 场景状态
            if self._target_scene_state:
                try:
                    dlg.load_scene_state(self._target_scene_state)
                except Exception:
                    pass
            dlg.valuesChanged.connect(self._on_target_values_changed)
            dlg.closed.connect(self._on_target_dlg_closed)
            dlg.show()
            self._target_dlg = dlg
        except Exception as ex:
            import traceback
            traceback.print_exc()
            QMessageBox.warning(
                self, _T('hint'),
                u"目标控制窗口打开失败：%r" % (ex,))

    def _on_target_values_changed(self):
        """目标控制窗口改动 → 刷新表达式 / 画布 / 飞行数据窗口。"""
        self.update_variables()
        self.canvas.eval_all(0.0)
        self.canvas.update()
        try:
            self.panel.refresh_preview()
        except Exception:
            pass
        if self._flight_dlg is not None and self._flight_dlg.isVisible():
            self._flight_dlg.set_values(self._collect_all_values())
        if getattr(self, '_settings_enabled', False):
            try:
                self._settings_timer.start()
            except Exception:
                pass

    def _on_target_dlg_closed(self):
        # ★ 关闭前保存场景状态
        try:
            if self._target_dlg is not None:
                self._target_scene_state = self._target_dlg.get_scene_state()
        except Exception:
            pass
        self._target_dlg = None

    def _on_cse_level_changed(self):
        try:
            self._cse_level = self.cmb_cse_level.currentData() or 'mid'
        except Exception:
            self._cse_level = 'mid'
        try:
            self.refresh_output()
        except Exception:
            pass

    def _clean_var_prefix(self, raw=None):
        """清洗前缀：
        · 去掉首尾空白
        · 去掉所有非 [A-Za-z0-9_] 字符
        · 若首字符是数字则前面补下划线
        · 为空则回落到 'V'
        """
        if raw is None:
            try:
                raw = self.edit_var_prefix.text() or u""
            except Exception:
                raw = u""
        s = re.sub(r'[^A-Za-z0-9_]', u'', (raw or u"").strip())
        if not s:
            return u'V'
        if re.match(r'^[0-9]', s):
            s = u"_" + s
        return s

    def _prefix_conflicts(self, prefix):
        """判断前缀 P 生成的 P1..Pn 是否与内置变量/函数/自定义变量冲突。"""
        if not prefix:
            return False
        try:
            reserved = set(self._reserved_var_names())
        except Exception:
            reserved = set()
        try:
            for d in self._custom_vars:
                n = d.get('name', u"") if isinstance(d, dict) else u""
                if n:
                    reserved.add(n)
        except Exception:
            pass
        # 前缀本身也算非法（用户可能直接当变量名用）
        if prefix in reserved:
            return True
        # 生成的前缀 + 数字 也要检查
        for i in range(1, 41):
            if (u"%s%d" % (prefix, i)) in reserved:
                return True
        return False

    def _validate_var_prefix_style(self):
        """根据当前前缀是否冲突，给输入框红/正常样式。"""
        try:
            prefix = self._clean_var_prefix()
            bad = self._prefix_conflicts(prefix)
        except Exception:
            bad = False
        try:
            if bad:
                self.edit_var_prefix.setStyleSheet(
                    "background-color:#ffcccc; border:1px solid #ff0000;")
            else:
                self.edit_var_prefix.setStyleSheet("")
        except Exception:
            pass
        return not bad

    def _on_var_prefix_text_changed(self, text):
        """实时过滤非法字符 + 更新红框。"""
        try:
            raw = text or u""
            # 非法字符立即过滤掉
            cleaned = re.sub(r'[^A-Za-z0-9_]', u'', raw)
            if cleaned and re.match(r'^[0-9]', cleaned):
                cleaned = u"_" + cleaned
            if cleaned != raw:
                self.edit_var_prefix.blockSignals(True)
                self.edit_var_prefix.setText(cleaned)
                self.edit_var_prefix.blockSignals(False)
        except Exception:
            pass
        # 红框 / 正常
        try:
            self._validate_var_prefix_style()
        except Exception:
            pass

    def _on_var_prefix_changed(self):
        """前缀最终确定（回车 / 失焦）：
        · 冲突 → 红框，不重新生成（保留上次有效输出）
        · 合法 → 规范显示 + 重新生成输出
        """
        try:
            cleaned = self._clean_var_prefix()
            self.edit_var_prefix.blockSignals(True)
            self.edit_var_prefix.setText(cleaned)
            self.edit_var_prefix.blockSignals(False)
        except Exception:
            pass
        if not self._validate_var_prefix_style():
            # 冲突：显示提示，但不刷新输出
            try:
                self.statusBar().showMessage(_L(
                    u"前缀与现有变量或函数重名，请换一个（不会生效）",
                    u"Prefix clashes with existing variables or functions; "
                    u"please choose another (not applied)"), 4000)
            except Exception:
                pass
            return
        try:
            self.refresh_output()
        except Exception:
            pass

    def _cse_params(self):
        """返回 (max_vars, min_count, min_len, post_max_defs)，
        对应低/中/高压缩强度"""
        try:
            lvl = self.cmb_cse_level.currentData()
        except Exception:
            lvl = getattr(self, '_cse_level', 'mid')
        if lvl == 'low':
            # 只做极少量的长提取
            return 8,  3, 20, 8
        if lvl == 'high':
            # 极致压缩：允许更多定义，但强后处理仍会大幅削减
            return 60, 2, 4, 24
        # mid
        return 30, 2, 8, 16

    def _on_custom_vars_toggled(self, checked):
        """输出栏“自定义变量”按钮：
        · 打开：右侧“自定义变量 / 函数”面板可见，并启用 CSE
        · 关闭：右侧面板隐藏，输出不再提取自定义变量
        """
        try:
            self._var_wrap.setVisible(bool(checked))
        except Exception:
            pass
        # ★ 打开时若右侧被压成 0 宽，强制给足宽度（否则看不见）
        if checked:
            try:
                sizes = self._output_split.sizes()
                total = sum(sizes) if sizes else 0
                if total <= 0:
                    total = self._output_split.width() or 800
                if len(sizes) < 2 or sizes[1] < 180:
                    right_w = 480
                    left_w = max(160, total - right_w)
                    self._output_split.setSizes([left_w, right_w])
            except Exception:
                pass
        # 面板状态变化后重新生成输出
        try:
            self.refresh_output()
        except Exception:
            pass
        # 重新计算列组布局（面板隐藏时列宽可能变化）
        try:
            QTimer.singleShot(0, self._refresh_var_layout)
        except Exception:
            pass
        # ★ 面板显隐变化 → 刷新"显示控制面板"按钮位置
        try:
            self._update_show_ctrl_btn()
        except Exception:
            pass

    def _sync_custom_var_names_to_panel(self):
        try:
            names = [d.get('name', u"") for d in self._custom_vars
                     if d.get('name')]
            self.panel.set_custom_var_names(names)
        except Exception:
            pass

    def _on_custom_vars_changed(self):
        self.update_variables()
        self.canvas.eval_all(0.0)
        self.canvas.update()
        try:
            self.panel.refresh_preview()
        except Exception:
            pass
        # ★ 同步到「插入变量」菜单
        self._sync_custom_var_names_to_panel()
        # ★ 自定义变量名变了 → 重新校验前缀红框
        try:
            self._validate_var_prefix_style()
        except Exception:
            pass
        if getattr(self, '_settings_enabled', False):
            try:
                self._settings_timer.start()
            except Exception:
                pass

    def _on_custom_vars_closed(self):
        # 该回调仅用于兼容旧对话框路径；现在面板直接内嵌在输出栏，不再需要
        self._custom_vars_dlg = None

    # ---------------- 飞行数据对话框 ----------------
    def show_flight_data(self):
        if self._flight_dlg is not None and self._flight_dlg.isVisible():
            self._flight_dlg.raise_();
            self._flight_dlg.activateWindow();
            return
        self._flight_dlg_time_was_enabled = self.time_control.chk.isChecked()
        self.time_control.chk.setChecked(False)
        dlg = FlightDataDialog(None)
        dlg.setWindowFlag(Qt.WindowStaysOnTopHint, False)
        dlg.valueChanged.connect(self._on_flight_dlg_changed)
        dlg.resetOneRequested.connect(self._on_flight_dlg_reset_one)
        dlg.resetAllRequested.connect(self._on_flight_dlg_reset_all)
        dlg.closed.connect(self._on_flight_dlg_closed)
        dlg.set_values(self._collect_all_values())
        dlg.show()
        self._flight_dlg = dlg

    def _collect_all_values(self):
        vals = self.get_control_values()
        d = {
            'Throttle': vals['throttle'], 'Yaw': vals['yaw'],
            'Pitch': vals['pitch'], 'Roll': vals['roll'],
            'Brake': vals['brake_axis'], 'Heading': vals['heading'],
            'VTOL': vals['vtol'], 'Trim': vals['trim'],
        }
        d.update(self._flight_data)
        return d

    def _on_flight_dlg_changed(self, key, value):
        ctrl_keys = {'Throttle', 'Yaw', 'Pitch', 'Roll', 'Brake',
                     'Heading', 'VTOL', 'Trim'}
        if key in ctrl_keys: self._apply_ctrl_value(key, value)
        if key in self._flight_data: self._flight_data[key] = value
        # ★ 姿态数据同步到姿态仪和数值框（摇杆不联动）
        if key in ('PitchAngle', 'RollAngle'):
            try:
                pitch = self._flight_data.get('PitchAngle', 0.0)
                roll = self._flight_data.get('RollAngle', 0.0)
                self.attitude_indicator.set_attitude(pitch, roll)
                self.lbl_pitch_val.setText(u"%.4f" % pitch)
                self.lbl_roll_val.setText(u"%.4f" % roll)
            except Exception:
                pass
        self.update_variables()
        self.canvas.eval_all(0.0);
        self.canvas.update()
        self.panel.refresh_preview()
        if self._floating_panel is not None:
            try:
                aoa = self._flight_data.get('AngleOfAttack', 0.0)
                self._floating_panel.aoa_knob.set_value(aoa)
                self._floating_panel.speed_knob.set_values(self._flight_data)
            except Exception:
                pass
        # ★ 同步目标控制窗口显示
        try:
            if self._target_dlg is not None and self._target_dlg.isVisible():
                self._target_dlg.refresh_from_data()
        except Exception:
            pass

    def _apply_ctrl_value(self, key, value):
        try:
            if key == 'Yaw':
                jly = self.joystick_left.y()
                self.joystick_left.area.blockSignals(True)
                self.joystick_left.set_value(float(value), jly)
                self.joystick_left.area.blockSignals(False)
                self.joystick_left._sync_spins_from_area()
            elif key == 'Throttle':
                jlx = self.joystick_left.x()
                self.joystick_left.area.blockSignals(True)
                self.joystick_left.set_value(jlx, max(0.0, min(1.0, float(value))))
                self.joystick_left.area.blockSignals(False)
                self.joystick_left._sync_spins_from_area()
            elif key == 'Brake':
                if self.brake_btn.isChecked(): return
                jlx = self.joystick_left.x()
                self.joystick_left.area.blockSignals(True)
                self.joystick_left.set_value(jlx, -max(0.0, min(1.0, float(value))))
                self.joystick_left.area.blockSignals(False)
                self.joystick_left._sync_spins_from_area()
            elif key == 'Pitch':
                jlx = self.joystick_right.x()
                self.joystick_right.area.blockSignals(True)
                self.joystick_right.set_value(jlx, float(value))
                self.joystick_right.area.blockSignals(False)
                self.joystick_right._sync_spins_from_area()
            elif key == 'Roll':
                jly = self.joystick_right.y()
                self.joystick_right.area.blockSignals(True)
                self.joystick_right.set_value(float(value), jly)
                self.joystick_right.area.blockSignals(False)
                self.joystick_right._sync_spins_from_area()
            elif key == 'Heading':
                self.heading_knob.dial.blockSignals(True)
                self.heading_knob.dial.set_value(float(value))
                self.heading_knob.dial.blockSignals(False)
                self.heading_knob.spin.blockSignals(True)
                self.heading_knob.spin.setValue(float(value))
                self.heading_knob.spin.blockSignals(False)
            elif key == 'VTOL':
                self.slider_vtol.slider.blockSignals(True)
                self.slider_vtol.set_value(float(value))
                self.slider_vtol.slider.blockSignals(False)
                self.slider_vtol.value_spin.blockSignals(True)
                self.slider_vtol.value_spin.setValue(float(value))
                self.slider_vtol.value_spin.blockSignals(False)
            elif key == 'Trim':
                self.slider_trim.slider.blockSignals(True)
                self.slider_trim.set_value(float(value))
                self.slider_trim.slider.blockSignals(False)
                self.slider_trim.value_spin.blockSignals(True)
                self.slider_trim.value_spin.setValue(float(value))
                self.slider_trim.value_spin.blockSignals(False)
        except Exception:
            pass

    def _on_flight_dlg_reset_one(self, key):
        for name, lo, hi, default in (
                FlightDataDialog.CTRL_FIELDS + FlightDataDialog.FLIGHT_FIELDS):
            if name == key:
                if self._flight_dlg is not None:
                    self._flight_dlg.set_one(key, default)
                    self._flight_dlg.valueChanged.emit(key, default)
                return

    def _on_flight_dlg_reset_all(self):
        defaults = {}
        for name, lo, hi, default in (
                FlightDataDialog.CTRL_FIELDS + FlightDataDialog.FLIGHT_FIELDS):
            defaults[name] = default
        if self._flight_dlg is not None:
            self._flight_dlg.set_values(defaults)
            for k, v in defaults.items():
                self._flight_dlg.valueChanged.emit(k, v)

    def _on_flight_dlg_closed(self):
        if self._flight_dlg_time_was_enabled:
            self.time_control.chk.setChecked(True)
        self._flight_dlg = None

    # ---------------- 语言 ----------------
    def _on_lang_changed(self, idx):
        global CURRENT_LANG
        lang = self.cmb_lang.currentData()
        if not lang: return
        CURRENT_LANG = lang
        try:
            app = QApplication.instance()
            t = getattr(app, '_qt_trans_zh', None)
            if t is not None:
                app.removeTranslator(t)
                if CURRENT_LANG == 'zh':
                    app.installTranslator(t)
        except Exception:
            pass
        self._apply_language()
        # ★ 语言变化后触发一次自动保存
        if getattr(self, '_settings_enabled', False):
            try:
                self._settings_timer.start()
            except Exception:
                pass

    def _apply_language(self):
        self.setWindowTitle(_T('title') + u"  v" + APP_VERSION)
        tr = ZH_EN_MAP if CURRENT_LANG == 'en' else EN_ZH_MAP


        def translate_widget(w):
            try:
                if isinstance(w, QGroupBox):
                    t = w.title()
                    if t in tr: w.setTitle(tr[t])
                elif hasattr(w, 'text') and hasattr(w, 'setText'):
                    t = w.text()
                    if t in tr: w.setText(tr[t])
            except Exception:
                pass

        def translate_action(a):
            try:
                t = a.text()
                if t in tr: a.setText(tr[t])
            except Exception:
                pass

        def translate_all(root):
            for w in root.findChildren(QWidget): translate_widget(w)
            for a in root.findChildren(QAction): translate_action(a)

        translate_all(self)

        # ---- 工具栏标签 ----
        try:
            self.lbl_canvas_w.setText(_T('canvas_w'))
            self.lbl_canvas_h.setText(_T('canvas_h'))
            self.lbl_global_size.setText(_T('global_size'))
            self.lbl_grid_spacing.setText(_T('grid_spacing'))
        except Exception:
            pass

        # ---- 属性面板辅助线分组框 ----
        try:
            self.panel.gb_helpers.setTitle(_T('helpers_menu'))
            self.panel.btn_tool_point.setText(_T('point_lbl'))
            self.panel.btn_tool_line.setText(_T('line_lbl'))
            self.panel.btn_tool_circle.setText(_T('circle_lbl'))
            self.panel.btn_snap_grid.setText(_T('snap_grid'))
            self.panel.btn_snap_helpers.setText(_T('char_snap'))
            self.panel.btn_lock_helpers.setText(_T('lock_helpers'))
            self.panel.btn_bind.setText(_T('bind_btn'))
            self.panel.btn_unbind.setText(_T('unbind_btn'))
            self.panel.btn_unbind_all.setText(_T('unbind_all_btn'))
        except Exception:
            pass

        # ---- 字符选择表按钮 ----
        try:
            self.charlist.title_label.setText(_T('char_table'))
            self.charlist.btn_new_folder.setText(_T('new_folder'))
            self.charlist.btn_rename.setText(_T('rename'))
            self.charlist.btn_delete.setText(_T('del'))
            self.charlist.btn_dual.setText(
                _T('single') if self.charlist._dual_mode else _T('dual'))
            self.charlist.btn_vis.setText(_T('hide_show'))
            self.charlist.btn_up.setText(_T('move_up'))
            self.charlist.btn_down.setText(_T('move_down'))
            self.charlist.btn_share.setText(_T('share'))
            self.charlist.btn_import.setText(_T('import'))
        except Exception:
            pass

        # ---- 自定义变量表 ----
        try:
            self.lbl_custom_vars.setText(_T('custom_vars_hdr'))
            self._set_var_table()
        except Exception:
            pass

        # ---- 前缀输入框 tooltip 同步 ----
        try:
            self.edit_var_prefix.setToolTip(_L(
                u"自定义函数变量的前缀\n"
                u"留空时使用默认 V（V1、V2、V3…）\n"
                u"例如输入 abc → abc1、abc2、abc3…\n"
                u"只允许字母 / 数字 / 下划线；不能与现有变量或函数重名",
                u"Prefix for custom variable names\n"
                u"Empty = default V (V1, V2, V3…)\n"
                u"e.g. 'abc' → abc1, abc2, abc3…\n"
                u"Only letters / digits / underscore; must not clash with "
                u"existing variables or functions"))
        except Exception:
            pass
        # 刷新红框状态（自定义变量变化后可能不再冲突）
        try:
            self._validate_var_prefix_style()
        except Exception:
            pass

        # ---- 语言下拉：标签 + 选项文字同步 ----
        try:
            self.lbl_lang.setText(u"  " + _L(u"Language", u"语言") + u": ")
        except Exception:
            pass
        try:
            self.cmb_lang.blockSignals(True)
            self.cmb_lang.setItemText(0, _L(u"Chinese", u"中文"))
            self.cmb_lang.setItemText(1, _L(u"English", u"英语"))
            idx = self.cmb_lang.findData(CURRENT_LANG)
            if idx >= 0:
                self.cmb_lang.setCurrentIndex(idx)
            self.cmb_lang.blockSignals(False)
        except Exception:
            pass

        # ---- CSE 启用 / 补偿偏移 文字 ----
        try:
            self.chk_cse.setText(_L(u"启用", u"Enable"))
        except Exception:
            pass
        try:
            self.panel.chk_compensate.setText(_L(u"补偿偏移", u"Offset Comp"))
            self.panel.chk_compensate.setToolTip(_L(
                u"开启后：当使用 FunkyTree 函数时，自动添加字符偏移补偿公式",
                u"When ON: automatically adds glyph offset compensation\n"
                u"when using FunkyTree expressions"))
        except Exception:
            pass

        # ---- 文本内容 placeholder ----
        try:
            self.panel.text_edit.setPlaceholderText(_L(
                u"输入字符，或用 {表达式} 求值",
                u"Enter text, or {expression} to evaluate"))
        except Exception:
            pass
        # ---- fx tooltip ----
        try:
            self.panel.chk_size_expr.setToolTip(_L(
                u"勾选则输出 size 函数栏的内容",
                u"When checked, output the size expression field"))
        except Exception:
            pass
        try:
            self.panel.chk_rot_expr.setToolTip(_L(
                u"勾选则输出 rotate 函数栏的内容",
                u"When checked, output the rotate expression field"))
        except Exception:
            pass
        try:
            self.panel.chk_pos_expr.setToolTip(_L(
                u"勾选则输出 pos 函数栏的内容",
                u"When checked, output the pos expression field"))
        except Exception:
            pass
        try:
            self.panel.chk_vo_expr.setToolTip(_L(
                u"勾选则输出 voffset 函数栏的内容",
                u"When checked, output the voffset expression field"))
        except Exception:
            pass
        # ---- 颜色按钮 ----
        try:
            self.panel.color_btn.setText(_L(
                u"文字颜色（默认 #000000）",
                u"Color (default #000000)"))
        except Exception:
            pass
        # ---- size 输入框 tooltip ----
        try:
            self.panel.size_spin.setToolTip(_L(
                u"字号：可输入小数（0.35）或百分比（35%）",
                u"Font size: enter a decimal (0.35) or percent (35%)"))
        except Exception:
            pass

        # ---- alpha / mark 标签 tooltip ----
        try:
            self.panel.btn_alpha_tag.setToolTip(_L(
                u"透明度标签（点击两次切换）\n"
                u"第一次：<alpha=#80>\n"
                u"第二次：<alpha=#FF>",
                u"Alpha tag (two-click toggle)\n"
                u"1st click: <alpha=#80>\n"
                u"2nd click: <alpha=#FF>"))
        except Exception:
            pass
        try:
            self.panel.btn_mark_tag.setToolTip(_L(
                u"背景色标签（点击两次成对插入）\n"
                u"第一次：<mark=#FFFF00>\n"
                u"第二次：</mark>",
                u"Mark tag (two-click pair insert)\n"
                u"1st click: <mark=#FFFF00>\n"
                u"2nd click: </mark>"))
        except Exception:
            pass

        # ---- 单独处理各按钮/标签的文字 ----
        try:
            self.time_control.chk.setText(_T('run_test'))
        except Exception:
            pass
        # ★ 输出标题栏（含字节数）随语言同步
        try:
            self._update_output_title_bytes()
        except Exception:
            try:
                self.output_title_label.setText(_T('output_title'))
            except Exception:
                pass
        try:
            if hasattr(self, 'btn_custom_vars'):
                self.btn_custom_vars.setText(_T('custom_vars_btn'))
        except Exception:
            pass
        # ★ 自定义变量面板标题同步
        try:
            self.lbl_custom_vars.setText(_T('custom_vars_hdr'))
        except Exception:
            pass

        # ★ 主控制面板左上角“飞行数据 / 自定义变量”按钮文字同步
        try:
            self.btn_flight_data_main.setText(_T('flight_data_btn'))
            self.btn_flight_data_main.setToolTip(_L(
                u"打开飞行数据模拟窗口",
                u"Open flight data simulation window"))
        except Exception:
            pass
        try:
            self.btn_custom_vars_main.setText(_T('custom_vars_btn'))
            self.btn_custom_vars_main.setToolTip(_L(
                u"打开自定义变量编辑窗口（可添加/删除变量，用滑块调节）",
                u"Open custom variable editor "
                u"(add/delete variables, adjust via slider)"))
        except Exception:
            pass
        # ★ 目标控制按钮
        try:
            self.btn_target_ctrl_main.setText(_T('target_ctrl_btn'))
            self.btn_target_ctrl_main.setToolTip(_L(
                u"打开目标控制窗口（目标航向 / 俯仰 / 距离 / 锁定状态）",
                u"Open target control "
                u"(heading / elevation / distance / lock status)"))
        except Exception:
            pass
        # ★ 目标控制对话框若开着，整体刷新一次文字
        try:
            if self._target_dlg is not None:
                self._target_dlg._apply_language()
        except Exception:
            pass
        # ★ 压缩程度标签 + 下拉项同步
        try:
            self.lbl_cse_level.setText(_T('cse_label'))
        except Exception:
            pass
        try:
            self.cmb_cse_level.blockSignals(True)
            self.cmb_cse_level.setItemText(0, _T('cse_low'))
            self.cmb_cse_level.setItemText(1, _T('cse_mid'))
            self.cmb_cse_level.setItemText(2, _T('cse_high'))
            self.cmb_cse_level.setToolTip(_T('cse_tip'))
            self.cmb_cse_level.blockSignals(False)
        except Exception:
            pass
        try:
            self.charlist.title_label.setText(_T('char_table'))
        except Exception:
            pass
        try:
            self.charlist.btn_dual.setText(
                _T('single') if self.charlist._dual_mode else _T('dual'))
        except Exception:
            pass
        try:
            if self._floating_panel is not None:
                self.btn_float_panel.setText(_T('dock_btn'))
            else:
                self.btn_float_panel.setText(_T('float_btn'))
        except Exception:
            pass
        try:
            self.btn_min.setText(_T('expand') if self._output_minimized
                                 else _T('minimize'))
        except Exception:
            pass
        try:
            self.btn_ctrl_min.setText(_T('expand') if self._ctrl_minimized
                                      else _T('minimize'))
        except Exception:
            pass
        # ★ 控制面板 tooltip 同步
        try:
            self.btn_ctrl_min.setToolTip(_L(
                u"隐藏控制面板",
                u"Hide control panel"))
        except Exception:
            pass
        try:
            self.btn_att_invert.setToolTip(_L(
                u"垂直反转（默认开启）\n"
                u"未按下：向上推 = 俯仰角减小（推杆低头）\n"
                u"按下后：向上推 = 俯仰角增大（拉杆抬头）",
                u"Invert vertical (ON by default)\n"
                u"Released: push up = pitch decreases (nose down)\n"
                u"Pressed: push up = pitch increases (nose up)"))
        except Exception:
            pass
        try:
            self.time_control.chk.setToolTip(_L(
                u"开启后 sum()/rate() 等函数随时间变化",
                u"When ON, sum()/rate() etc. advance with time"))
        except Exception:
            pass
        try:
            self.time_control.btn_reset.setToolTip(_L(
                u"时间归 0（同时清空函数状态）",
                u"Reset time to 0 (also clears function state)"))
        except Exception:
            pass
        # ★ “显示控制面板”按钮文字 + tooltip（两个位置都刷）
        for _btn in (getattr(self, 'btn_show_ctrl', None),
                     getattr(self, 'btn_show_ctrl_out', None)):
            if _btn is None:
                continue
            try:
                _btn.setText(
                    _L(u"▲ 显示控制面板", u"▲ Show Control Panel"))
                _btn.setToolTip(_L(
                    u"控制面板已最小化，点击可恢复显示",
                    u"Control panel is minimized; click to restore"))
            except Exception:
                pass
        # 刷新按钮位置
        try:
            self._update_show_ctrl_btn()
        except Exception:
            pass

        # ---- 状态栏默认提示 ----
        try:
            self._status_default = _L(
                u"滚轮缩放 | 中键/Alt+左键 平移 | {表达式} 求值",
                u"Wheel: zoom | Middle / Alt+LMB: pan | {expr}: evaluate")
            self.statusBar().showMessage(self._status_default)
        except Exception:
            pass

        # ---- 属性面板的按钮 ----
        try:
            self.panel.btn_insert_var.setText(_T('insert_var'))
        except Exception:
            pass
        try:
            self.panel.btn_insert_fn.setText(_T('insert_fn'))
        except Exception:
            pass
        try:
            self.panel.btn_insert_preset.setText(_T('insert_preset'))
        except Exception:
            pass
        # ★ 重建「插入预设」菜单（切语言后避免中文残留）
        try:
            self.panel._rebuild_insert_preset_menu()
        except Exception:
            pass
        try:
            self.panel.btn_add_char_quick.setText(_T('add_char_btn'))
        except Exception:
            pass

        # ---- 独立面板 ----
        if self._floating_panel is not None:
            try:
                self._floating_panel.setWindowTitle(_T('float_title'))
                translate_all(self._floating_panel)
                self._floating_panel.btn_flight_data.setText(_T('flight_data_btn'))
                self._floating_panel.btn_custom_vars.setText(_T('custom_vars_btn'))
                self._floating_panel.btn_target_ctrl.setText(_T('target_ctrl_btn'))
                self._floating_panel.btn_dock.setText(_T('dock_btn'))
            except Exception:
                pass

    # ---------------- 拖拽 JSON ----------------
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            for url in e.mimeData().urls():
                if url.isLocalFile():
                    p = url.toLocalFile().lower()
                    if p.endswith('.json'):
                        e.acceptProposedAction();
                        return
        e.ignore()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()

    def dropEvent(self, e):
        if not e.mimeData().hasUrls(): return
        for url in e.mimeData().urls():
            if not url.isLocalFile(): continue
            path = url.toLocalFile()
            if not path.lower().endswith('.json'): continue
            self._load_project_from_path(path)
            e.acceptProposedAction();
            return

    def _load_project_from_path(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as ex:
            QMessageBox.warning(self, _T('fail'), str(ex));
            return
        try:
            self._load_project_from_data(data)
        except RecursionError:
            QMessageBox.critical(
                self, u"加载失败",
                u"绑定关系里检测到循环引用，已中止加载。\n"
                u"请检查工程里的吸附关系是否成环（A→B→A）。")
        except Exception as ex:
            import traceback
            tb = traceback.format_exc()
            QMessageBox.critical(
                self, u"加载失败",
                u"%s\n\n--- 详细堆栈 ---\n%s" % (ex, tb[-1500:]))

    def _load_project_from_data(self, data):
        has_window_state = bool(data.get("window_state"))
        cs = data.get("canvas", {})
        self.canvas.canvas_w = float(cs.get("w", 1.0))
        self.canvas.canvas_h = float(cs.get("h", 1.0))
        self.canvas.global_size = float(data.get("global_size", DEFAULT_GLOBAL_SIZE))
        self.canvas.glyph_ratio = float(data.get("glyph_ratio", DEFAULT_GLYPH_RATIO))
        snap = data.get("snap", {})
        self.canvas.snap_enabled = bool(snap.get("enabled", True))
        self.canvas.snap_spacing = float(snap.get("spacing", 1.0))
        self.spin_w.setValue(self.canvas.canvas_w)
        self.spin_h.setValue(self.canvas.canvas_h)
        self.spin_global.setValue(self.canvas.global_size)
        self.spin_spacing.setValue(self.canvas.snap_spacing)
        controls = data.get("controls", {})
        if controls:
            acts = controls.get("activate", [])
            for i, b in enumerate(self.activate_btns):
                if i < len(acts): b.setChecked(acts[i] == 1)
            if "landing_gear" in controls:
                self.landing_btn.setChecked(controls["landing_gear"] == 0)
            if "brake" in controls:
                self.brake_btn.setChecked(controls["brake"] == 1)
            if "vtol" in controls: self.slider_vtol.set_value(controls["vtol"])
            if "trim" in controls: self.slider_trim.set_value(controls["trim"])
            if "heading" in controls:
                self.heading_knob.dial.set_value(controls["heading"])
                self.heading_knob.spin.blockSignals(True)
                self.heading_knob.spin.setValue(controls["heading"])
                self.heading_knob.spin.blockSignals(False)
            if "yaw" in controls and "throttle" in controls and "brake_axis" in controls:
                lx = controls["yaw"];
                th = controls["throttle"];
                br = controls["brake_axis"]
                ly = th if th > 0 else (-br if br > 0 else 0.0)
                self.joystick_left.set_value(lx, ly)
            if "pitch" in controls and "roll" in controls:
                self.joystick_right.set_value(controls["roll"], controls["pitch"])
        fd = data.get("flight_data")
        if fd: self._flight_data.update(fd)
        if "time" in data: self.time_control.set_time(data["time"])

        # ★ 自定义变量：没有该字段则保持原样（兼容老版本 / 减少容量）
        if "custom_vars" in data:
            self._custom_vars = []
            for d in data.get("custom_vars", []) or []:
                try:
                    if not isinstance(d, dict):
                        continue
                    n = str(d.get('name', '') or '')
                    if not n:
                        continue
                    self._custom_vars.append({
                        'name': n,
                        'value': float(d.get('value', 0.0)),
                        'min': float(d.get('min', -1.0)),
                        'max': float(d.get('max', 1.0)),
                    })
                except Exception:
                    continue
            # 若对话框开着，重建显示
            try:
                if (self._custom_vars_dlg is not None
                        and self._custom_vars_dlg.isVisible()):
                    self._custom_vars_dlg._rebuild()
            except Exception:
                pass
            # ★ 同步到「插入变量」菜单
            self._sync_custom_var_names_to_panel()

        # ★ 目标控制窗口的 3D 场景状态
        if "target_scene" in data:
            self._target_scene_state = data.get("target_scene")
            # 若对话框开着，同步刷新
            try:
                if (self._target_dlg is not None
                        and self._target_dlg.isVisible()):
                    self._target_dlg.load_scene_state(self._target_scene_state)
            except Exception:
                pass

        pts, lns, cirs = _decode_helpers(data.get("helpers", []))
        hlist = pts + lns + cirs

        tree_data = data.get("tree")
        if tree_data:
            nr = self._dict_to_node(tree_data, hlist)
            nr.parent = None;
            nr.folder = True
            self.canvas.root = nr
        else:
            self.canvas.root = Node(folder=True)
            items = [RichItem.from_dict(d) for d in data.get("items", [])]
            for it in items: self.canvas.append_item(it)
        self.canvas._resync_helper_lists()
        self._sync_helper_name_seq()
        self.canvas.selected = []
        self.canvas.selected_helpers = []
        self.canvas.selectionChanged.emit();
        self.canvas.itemsChanged.emit()
        self.update_variables()
        self.canvas.eval_all(0.0)
        self.canvas.update()
        # ★ 有窗口状态记录时不自动适配窗口（保留上次大小/位置）
        if not has_window_state:
            self.canvas.fit_view()
        self.refresh_output()
        self.panel.refresh_ranges()
        self.charlist.rebuild()
        self._on_brake_toggled(self.brake_btn.isChecked())
        self.statusBar().showMessage(_T('loaded'), 3000)
        self._push_undo_now()
        # ★ 恢复 UI 状态（压缩程度 / 变量前缀 / 显示开关 / 面板显隐）
        try:
            self._apply_ui_state(data.get("ui_state"))
        except Exception:
            pass
        # ★ 恢复窗口 / 子窗口状态
        if has_window_state:
            try:
                self._apply_window_state(data.get("window_state"))
            except Exception:
                pass
        # UI 状态恢复后重新生成一次输出（按新的压缩程度 / 前缀）
        try:
            self.refresh_output()
        except Exception:
            pass

    # ---------------- 工具栏 ----------------
    def _build_toolbar(self):
        tb = QToolBar(u"主工具栏");
        tb.setMovable(False);
        self.addToolBar(tb)

        def add(text, slot, tip=None):
            a = QAction(text, self);
            a.triggered.connect(slot)
            if tip: a.setToolTip(tip)
            tb.addAction(a);
            return a

        add(_T('add_char'), self.add_char)
        add(_T('duplicate'), self.canvas.duplicate_selected)
        add(_T('delete'), self.canvas.delete_selected)
        tb.addSeparator()
        sym_btn = QToolButton()
        sym_btn.setText(_T('insert_sym'))
        sym_btn.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(sym_btn)
        for label, text, rot in SYMBOL_MENU_ITEMS:
            a = menu.addAction(label)
            a.triggered.connect(
                lambda c=False, ch=text, r=rot: self.add_symbol(ch, r))
        sym_btn.setMenu(menu);
        tb.addWidget(sym_btn)
        tb.addSeparator()
        self.lbl_canvas_w = QLabel(_T('canvas_w'))
        tb.addWidget(self.lbl_canvas_w)
        self.spin_w = CanvasSizeSpin()
        self.spin_w.setValue(1.0)
        self.spin_w.setFixedWidth(70)
        self.spin_w.valueChanged.connect(self._on_canvas_size)
        tb.addWidget(self.spin_w)
        self.lbl_canvas_h = QLabel(_T('canvas_h'))
        tb.addWidget(self.lbl_canvas_h)
        self.spin_h = CanvasSizeSpin()
        self.spin_h.setValue(1.0)
        self.spin_h.setFixedWidth(70)
        self.spin_h.valueChanged.connect(self._on_canvas_size)
        tb.addWidget(self.spin_h)
        tb.addSeparator()
        self.lbl_global_size = QLabel(_T('global_size'))
        tb.addWidget(self.lbl_global_size)
        self.spin_global = QDoubleSpinBox()
        self.spin_global.setRange(0.00001, 100.0);
        self.spin_global.setDecimals(5)
        self.spin_global.setKeyboardTracking(False)
        self.spin_global.setSingleStep(0.5);
        self.spin_global.setValue(DEFAULT_GLOBAL_SIZE)
        self.spin_global.setFixedWidth(100)
        self.spin_global.valueChanged.connect(self._on_global_size)
        tb.addWidget(self.spin_global)
        tb.addSeparator()
        add(_T('fit_view'), self.canvas.fit_view)
        self.lbl_grid_spacing = QLabel(_T('grid_spacing'))
        tb.addWidget(self.lbl_grid_spacing)
        self.spin_spacing = SpacingSpin()
        self.spin_spacing.setValue(1.0)
        self.spin_spacing.setFixedWidth(72)   # ★ 从 90 缩到 72
        self.spin_spacing.valueChanged.connect(self._on_spacing_changed)
        tb.addWidget(self.spin_spacing)
        more_btn = QToolButton();
        more_btn.setText(_T('more'))
        more_btn.setPopupMode(QToolButton.InstantPopup)
        m = QMenu(more_btn)
        self.act_var_list = QAction(_T('var_list'), self)
        self.act_var_list.triggered.connect(self.show_var_list)
        m.addAction(self.act_var_list)
        self.act_flight_data = QAction(_T('flight_data'), self)
        self.act_flight_data.triggered.connect(self.show_flight_data)
        m.addAction(self.act_flight_data)
        self.act_custom_vars = QAction(_T('custom_vars_menu'), self)
        self.act_custom_vars.triggered.connect(self.show_custom_vars)
        m.addAction(self.act_custom_vars)
        m.addSeparator()
        m.addAction(_T('import_rich'), self.import_rich)
        m.addAction(_T('export_png'), self.export_png)
        m.addSeparator()
        m.addAction(_T('save_proj'), self.save_project)
        m.addAction(_T('open_proj'), self.open_project)
        m.addSeparator()
        g = QAction(_T('show_grid'), self, checkable=True, checked=True)
        g.toggled.connect(lambda v: (setattr(self.canvas, "show_grid", bool(v)),
                                     self.canvas.update()))
        m.addAction(g)
        b = QAction(_T('show_bounds'), self, checkable=True, checked=True)
        b.toggled.connect(lambda v: (setattr(self.canvas, "show_bounds", bool(v)),
                                     self.canvas.update()))
        m.addAction(b)
        r = QAction(_T('show_ruler'), self, checkable=True, checked=True)
        r.toggled.connect(lambda v: (setattr(self.canvas, "show_ruler", bool(v)),
                                     self.canvas.update()))
        m.addAction(r)
        m.addSeparator()
        m.addAction(_T('save_settings'), self._on_save_settings)
        # ★ act_ctrl_toggle 仍保留（供右键菜单 / 控制面板最小化逻辑使用），
        #   但不再加入"更多"菜单
        self.act_ctrl_toggle = QAction(_T('menu_ctrl'), self)
        self.act_ctrl_toggle.setCheckable(True);
        self.act_ctrl_toggle.setChecked(True)
        self.act_ctrl_toggle.toggled.connect(self._toggle_ctrl_visible)
        more_btn.setMenu(m);
        tb.addWidget(more_btn)
        tb.addSeparator()
        # ★ 反向：中文模式显示 "Language:"，英文模式显示 "语言:"
        self.lbl_lang = QLabel(u"  " + _L(u"Language", u"语言") + u": ")
        tb.addWidget(self.lbl_lang)
        self.cmb_lang = QComboBox()
        # ★ 中文模式：Chinese / 英语
        #   英文模式：中文 / 英语
        self.cmb_lang.addItem(_L(u"Chinese", u"中文"), "zh")
        self.cmb_lang.addItem(_L(u"English", u"英语"), "en")
        self.cmb_lang.setFixedWidth(90)
        self.cmb_lang.currentIndexChanged.connect(self._on_lang_changed)
        tb.addWidget(self.cmb_lang)

    def show_var_list(self):
        self.update_variables()
        custom_names = [d.get('name', u"") for d in self._custom_vars
                        if d.get('name')]
        VarListDialog(self.canvas.variables, self,
                      custom_names=custom_names).exec_()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # ★ 窗口尺寸变化 → 触发自定义函数列数重排（节流）
        try:
            if hasattr(self, '_var_resize_timer'):
                self._var_resize_timer.start()
        except Exception:
            pass

    def changeEvent(self, e):
        super().changeEvent(e)
        # ★ 最大化/还原状态变化也触发一次重排
        try:
            if e.type() == QEvent.WindowStateChange:
                if hasattr(self, '_var_resize_timer'):
                    self._var_resize_timer.start()
        except Exception:
            pass

    def _on_canvas_size(self):
        self.canvas.canvas_w = float(self.spin_w.value())
        self.canvas.canvas_h = float(self.spin_h.value())
        # 不再强制夹紧元素位置
        self.panel.refresh_ranges();
        self.panel.refresh()
        self.canvas.update();
        self.refresh_output()

    def _on_global_size(self, v):
        new_g = round(float(v), 5)
        self.canvas.global_size = new_g
        for it in self.canvas.items:
            if not it.size_is_custom: it.size = new_g
        self.canvas.eval_all(0.0);
        self.canvas.update();
        self.panel.refresh()
        self.charlist.refresh_texts();
        self.refresh_output()

    def _on_spacing_changed(self, v):
        self.canvas.snap_spacing = float(v);
        self.canvas.update()

    def _cascade_update_line_lengths(self):
        """把绑定到辅助线的字符公式，升级为"动态线长"版本。
        纯字符串操作 + 逐项 try，避免任何异常导致崩溃。"""
        try:
            byname = self.canvas._all_objects_by_name()
        except Exception:
            return
        changed = False
        for it in self.canvas.items:
            try:
                tgt = getattr(it, 'bind_to', u"")
                if not tgt: continue
                line = byname.get(tgt)
                if not isinstance(line, HelperLine): continue
                dx = getattr(it, 'bind_dx_expr', u'') or u''
                if not dx.strip(): continue

                L_expr = (u"sqrt(({%s_X2}-{%s_X1})*({%s_X2}-{%s_X1})"
                          u"+({%s_Y2}-{%s_Y1})*({%s_Y2}-{%s_Y1}))"
                          % (tgt, tgt, tgt, tgt, tgt, tgt, tgt, tgt))

                # 从末尾找最后一个 '*' 切分
                idx = dx.rfind(u'*')
                if idx <= 0: continue
                prefix = dx[:idx].strip()
                suffix = dx[idx + 1:].strip()
                if not prefix: continue

                # 后缀是否代表"长度"
                is_length = False
                # (a) 纯数字
                try:
                    float(suffix)
                    is_length = True
                except ValueError:
                    pass
                # (b) sqrt(...) → 已是新版
                if not is_length and suffix.startswith(u"sqrt(") and suffix.endswith(u")"):
                    # 已是新公式；只清理残留 dy
                    dy = getattr(it, 'bind_dy_expr', u'') or u''
                    dy_s = dy.strip()
                    if dy_s and dy_s not in (u'0', u'0.0', u'0.00'):
                        it.bind_dy_expr = u"0"
                        changed = True
                    continue
                # (c) v4 错误公式
                if not is_length:
                    v4_suffix = u"(({%s_X2})-({%s_X1}))" % (tgt, tgt)
                    if suffix == v4_suffix:
                        is_length = True

                if not is_length:
                    continue

                new_dx = u"%s*(%s)" % (prefix, L_expr)
                if new_dx == dx:
                    continue
                it.bind_dx_expr = new_dx
                dy = getattr(it, 'bind_dy_expr', u'') or u''
                dy_s = dy.strip()
                if dy_s and dy_s not in (u'0', u'0.0', u'0.00'):
                    it.bind_dy_expr = u"0"
                changed = True
            except Exception:
                continue

        if changed:
            try:
                self.canvas.eval_all(0.0)
            except Exception:
                pass
            try:
                self.canvas.update()
            except Exception:
                pass

    def _collect_ui_state(self):
        """收集与压缩程度 / 变量前缀 / 显示开关 / 面板显隐相关的一切 UI 状态"""
        st = {}
        # ---- 语言 ----
        try:
            st['lang'] = CURRENT_LANG
        except Exception:
            st['lang'] = 'zh'
        # ---- CSE 压缩程度 ----
        try:
            st['cse_level'] = self.cmb_cse_level.currentData() or 'mid'
        except Exception:
            st['cse_level'] = getattr(self, '_cse_level', 'mid')
        # ---- 自定义函数变量名前缀 ----
        try:
            st['var_prefix'] = self.edit_var_prefix.text() or u'V'
        except Exception:
            st['var_prefix'] = u'V'
        # ---- 输出栏右侧“自定义函数”面板是否显示 ----
        try:
            st['custom_vars_panel_open'] = bool(self.btn_custom_vars.isChecked())
        except Exception:
            st['custom_vars_panel_open'] = True
        # ---- 输出栏“自动刷新” ----
        try:
            st['autoupdate'] = bool(self.chk_autoupdate.isChecked())
        except Exception:
            st['autoupdate'] = True
        # ---- 输出 / 控制面板最小化 ----
        try:
            st['output_minimized'] = bool(self._output_minimized)
        except Exception:
            st['output_minimized'] = False
        try:
            st['ctrl_minimized'] = bool(self._ctrl_minimized)
        except Exception:
            st['ctrl_minimized'] = False
        # ---- 画布显示开关 ----
        try:
            st['show_grid'] = bool(self.canvas.show_grid)
        except Exception:
            st['show_grid'] = True
        try:
            st['show_bounds'] = bool(self.canvas.show_bounds)
        except Exception:
            st['show_bounds'] = True
        try:
            st['show_ruler'] = bool(self.canvas.show_ruler)
        except Exception:
            st['show_ruler'] = True
        return st

    def _apply_ui_state(self, st):
        """恢复上面的 UI 状态"""
        if not st:
            return
        # ---- 语言 ----
        try:
            global CURRENT_LANG
            lang = st.get('lang')
            if lang in ('zh', 'en') and lang != CURRENT_LANG:
                CURRENT_LANG = lang
                try:
                    app = QApplication.instance()
                    t = getattr(app, '_qt_trans_zh', None)
                    if t is not None:
                        app.removeTranslator(t)
                        if CURRENT_LANG == 'zh':
                            app.installTranslator(t)
                except Exception:
                    pass
                idx = self.cmb_lang.findData(lang)
                if idx >= 0:
                    self.cmb_lang.blockSignals(True)
                    self.cmb_lang.setCurrentIndex(idx)
                    self.cmb_lang.blockSignals(False)
                self._apply_language()
        except Exception:
            pass
        # ---- CSE 压缩程度 ----
        try:
            lvl = st.get('cse_level')
            if lvl in ('low', 'mid', 'high'):
                self._cse_level = lvl
                idx = self.cmb_cse_level.findData(lvl)
                if idx >= 0:
                    self.cmb_cse_level.blockSignals(True)
                    self.cmb_cse_level.setCurrentIndex(idx)
                    self.cmb_cse_level.blockSignals(False)
        except Exception:
            pass
        # ---- 变量名前缀 ----
        try:
            prefix = st.get('var_prefix') or u'V'
            self.edit_var_prefix.blockSignals(True)
            self.edit_var_prefix.setText(prefix)
            self.edit_var_prefix.blockSignals(False)
            self._validate_var_prefix_style()
        except Exception:
            pass
        # ---- 输出栏右侧面板显隐 ----
        try:
            want = bool(st.get('custom_vars_panel_open', True))
            self.btn_custom_vars.blockSignals(True)
            self.btn_custom_vars.setChecked(want)
            self.btn_custom_vars.blockSignals(False)
            self._var_wrap.setVisible(want)
            if want:
                try:
                    sizes = self._output_split.sizes()
                    total = sum(sizes) if sizes else 0
                    if total <= 0:
                        total = self._output_split.width() or 800
                    if len(sizes) < 2 or sizes[1] < 180:
                        right_w = 480
                        left_w = max(160, total - right_w)
                        self._output_split.setSizes([left_w, right_w])
                except Exception:
                    pass
        except Exception:
            pass
        # ★ 刷新"显示控制面板"按钮位置
        try:
            self._update_show_ctrl_btn()
        except Exception:
            pass
        # ★ 刷新"显示控制面板"按钮位置
        try:
            self._update_show_ctrl_btn()
        except Exception:
            pass
        # ---- 自动刷新 ----
        try:
            if 'autoupdate' in st:
                self.chk_autoupdate.blockSignals(True)
                self.chk_autoupdate.setChecked(bool(st['autoupdate']))
                self.chk_autoupdate.blockSignals(False)
        except Exception:
            pass
        # ---- 显示开关 ----
        try:
            if 'show_grid' in st:
                self.canvas.show_grid = bool(st['show_grid'])
            if 'show_bounds' in st:
                self.canvas.show_bounds = bool(st['show_bounds'])
            if 'show_ruler' in st:
                self.canvas.show_ruler = bool(st['show_ruler'])
            self.canvas.update()
        except Exception:
            pass
        # ---- 输出/控制面板最小化 ----
        try:
            if st.get('output_minimized') and not self._output_minimized:
                self._toggle_output_min()
            if st.get('ctrl_minimized') and not self._ctrl_minimized:
                try:
                    self.act_ctrl_toggle.setChecked(False)
                except Exception:
                    pass
        except Exception:
            pass

    def _collect_project_data(self):
        """收集和“保存工程”一样的数据快照（供设置自动保存复用）"""
        # ★ 如果目标控制窗口开着，顺手把当前状态抓出来
        try:
            if self._target_dlg is not None:
                self._target_scene_state = self._target_dlg.get_scene_state()
        except Exception:
            pass
        pts = self.canvas.helper_points
        lns = self.canvas.helper_lines
        cirs = self.canvas.helper_circles
        hlist = pts + lns + cirs
        hidx = {id(h): i for i, h in enumerate(hlist)}
        return {
            "version": APP_VERSION,
            "canvas": {"w": self.canvas.canvas_w,
                       "h": self.canvas.canvas_h},
            "global_size": self.canvas.global_size,
            "glyph_ratio": self.canvas.glyph_ratio,
            "snap": {"enabled": self.canvas.snap_enabled,
                     "spacing": self.canvas.snap_spacing},
            "controls": self.get_control_values(),
            "flight_data": self._flight_data,
            "time": self.time_control.value(),
            "tree": self._node_to_dict(self.canvas.root, hidx),
            "helpers": _encode_helpers(pts, lns, cirs),
            "custom_vars": list(self._custom_vars),
            # ★ 目标控制窗口的 3D 场景状态
            "target_scene": self._target_scene_state,
            # ★ 窗口 / 子窗口状态（尺寸、位置、是否打开）
            "window_state": self._collect_window_state(),
            # ★ 压缩程度 / 变量前缀 / 显示开关 / 面板显隐
            "ui_state": self._collect_ui_state(),
        }

    def _collect_window_state(self):
        st = {}
        try:
            st['main'] = _geo_to_b64(self)
            st['main_max'] = bool(self.isMaximized())
        except Exception:
            pass
        try:
            st['floating_panel'] = {
                'open': self._floating_panel is not None,
                'geo': (_geo_to_b64(self._floating_panel)
                        if self._floating_panel else None),
            }
        except Exception:
            pass
        try:
            open_fd = (self._flight_dlg is not None
                       and self._flight_dlg.isVisible())
            st['flight_data'] = {
                'open': open_fd,
                'geo': (_geo_to_b64(self._flight_dlg)
                        if self._flight_dlg else None),
            }
        except Exception:
            pass
        try:
            open_cv = (self._custom_vars_dlg is not None
                       and self._custom_vars_dlg.isVisible())
            st['custom_vars'] = {
                'open': open_cv,
                'geo': (_geo_to_b64(self._custom_vars_dlg)
                        if self._custom_vars_dlg else None),
            }
        except Exception:
            pass
        try:
            open_tc = (self._target_dlg is not None
                       and self._target_dlg.isVisible())
            st['target_ctrl'] = {
                'open': open_tc,
                'geo': (_geo_to_b64(self._target_dlg)
                        if self._target_dlg else None),
                'max': (bool(self._target_dlg.isMaximized())
                        if self._target_dlg else False),
            }
        except Exception:
            pass
        return st

    def _apply_window_state(self, st):
        """根据保存的窗口状态恢复主窗口 + 子窗口"""
        if not st:
            return
        # 主窗口
        try:
            if st.get('main'):
                _restore_geo(self, st['main'])
            if st.get('main_max'):
                self.showMaximized()
        except Exception:
            pass
        # 浮动控制面板
        try:
            fp = st.get('floating_panel', {}) or {}
            want = bool(fp.get('open'))
            have = self._floating_panel is not None
            if want and not have:
                self._do_float_panel()
            elif not want and have:
                self._do_dock_panel()
            if want and self._floating_panel is not None and fp.get('geo'):
                _restore_geo(self._floating_panel, fp['geo'])
        except Exception:
            pass
        # 飞行数据
        try:
            fd = st.get('flight_data', {}) or {}
            if fd.get('open'):
                self.show_flight_data()
                if self._flight_dlg is not None and fd.get('geo'):
                    _restore_geo(self._flight_dlg, fd['geo'])
        except Exception:
            pass
        # 自定义变量
        try:
            cv = st.get('custom_vars', {}) or {}
            if cv.get('open'):
                self.show_custom_vars()
                if self._custom_vars_dlg is not None and cv.get('geo'):
                    _restore_geo(self._custom_vars_dlg, cv['geo'])
        except Exception:
            pass
        # 目标控制窗口
        try:
            tc = st.get('target_ctrl', {}) or {}
            if tc.get('open'):
                self.show_target_control()
                if self._target_dlg is not None:
                    if tc.get('geo'):
                        _restore_geo(self._target_dlg, tc['geo'])
                    if tc.get('max'):
                        self._target_dlg.showMaximized()
        except Exception:
            pass

    def _auto_save_settings(self):
        if not getattr(self, '_settings_enabled', False):
            return
        if not getattr(self, '_settings_path', u""):
            return
        try:
            data = self._collect_project_data()
            with open(self._settings_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _on_save_settings(self):
        dlg = SaveSettingsDialog(
            getattr(self, '_settings_enabled', False),
            getattr(self, '_settings_path', u""), self)
        # 关闭窗口 / 取消 → 什么都不做
        if dlg.exec_() != QDialog.Accepted:
            return
        self._settings_enabled = dlg._result_enabled
        self._settings_path = dlg._result_path
        # ★ 同步到引导文件（下次启动自动读取）
        _save_bootstrap(self._settings_enabled, self._settings_path)
        if not self._settings_enabled:
            self.statusBar().showMessage(
                _L(u"已关闭设置保存", u"Settings save disabled"), 3000)
            return
        if dlg._result_overwrite:
            self._auto_save_settings()
            self.statusBar().showMessage(
                _L(u"设置已保存到: ", u"Settings saved to: ")
                + self._settings_path, 3000)
        else:
            self.statusBar().showMessage(
                _L(u"沿用原有设置文件: ", u"Using existing settings file: ")
                + self._settings_path, 3000)

    def _auto_load_settings_on_startup(self):
        """启动时读取引导文件，自动恢复上次的设置（窗口 + 内容）"""
        boot = _load_bootstrap()
        if not boot or not boot.get("enabled"):
            return
        path = boot.get("path", u"")
        if not path or not os.path.exists(path):
            return
        self._settings_enabled = True
        self._settings_path = path
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return
        try:
            self._load_project_from_data(data)
        except Exception:
            pass
        self.statusBar().showMessage(
            _L(u"已自动恢复设置", u"Settings restored"), 3000)

    def closeEvent(self, e):
        # ★ 关闭前保存一次（包含窗口状态、自定义变量、UI 状态、编辑内容）
        try:
            if getattr(self, '_settings_enabled', False) \
                    and getattr(self, '_settings_path', u""):
                # 阻塞定时器，避免同时触发多次写盘
                try:
                    self._settings_timer.stop()
                except Exception:
                    pass
                self._auto_save_settings()
        except Exception:
            pass
        try:
            _save_bootstrap(getattr(self, '_settings_enabled', False),
                            getattr(self, '_settings_path', u""))
        except Exception:
            pass
        super().closeEvent(e)

    def _on_content_changed(self):
        # ★ 先无条件升级旧公式（不管自动刷新开不开）
        try:
            self._cascade_update_line_lengths()
        except RecursionError:
            pass
        except Exception:
            pass
        if self.chk_autoupdate.isChecked():
            try:
                self.refresh_output()
            except RecursionError:
                pass
            except Exception:
                pass
        # ★ 自动保存设置（节流）
        if getattr(self, '_settings_enabled', False):
            try:
                self._settings_timer.start()
            except Exception:
                pass

    def add_char(self):
        c = self.canvas
        it = RichItem(_L(u"文本", u"text"), 0.0, 0.0, size=c.global_size)
        it.name = c._next_char_name()
        it.size_is_custom = False
        c.append_item(it)
        c.selected = [it]
        c.selectionChanged.emit()
        c.itemsChanged.emit()
        c.eval_all(0.0)
        c.update()
        c.contentChanged.emit()
        self.panel.focus_text()

    def add_char_at(self, wx, wy):
        """在指定世界坐标添加字符（右键菜单专用）；
        开启网格吸附时会吸附到最近网格。"""
        c = self.canvas
        if c.snap_enabled:
            try:
                wx = c._snap_world(wx)
                wy = c._snap_world(wy)
            except Exception:
                pass
        it = RichItem(_L(u"文本", u"text"), wx, wy, size=c.global_size)
        it.name = c._next_char_name()
        it.size_is_custom = False
        c.append_item(it)
        c.selected = [it]
        c.selectionChanged.emit()
        c.itemsChanged.emit()
        c.eval_all(0.0)
        c.update()
        c.contentChanged.emit()
        self.panel.focus_text()

    def add_symbol(self, ch, rotation=0.0):
        c = self.canvas
        it = RichItem(ch, 0.0, 0.0, size=c.global_size)
        it.name = c._next_char_name()
        it.size_is_custom = False
        if abs(rotation) > 1e-9:
            it.rotation = float(rotation)
        c.append_item(it)
        c.selected = [it]
        c.selectionChanged.emit()
        c.itemsChanged.emit()
        c.eval_all(0.0)
        c.update()
        c.contentChanged.emit()

    def add_symbol_at(self, ch, rotation, wx, wy):
        """在指定世界坐标添加符号（右键菜单专用）；
        开启网格吸附时会吸附到最近网格。"""
        c = self.canvas
        if c.snap_enabled:
            try:
                wx = c._snap_world(wx)
                wy = c._snap_world(wy)
            except Exception:
                pass
        it = RichItem(ch, wx, wy, size=c.global_size)
        it.name = c._next_char_name()
        it.size_is_custom = False
        if abs(rotation) > 1e-9:
            it.rotation = float(rotation)
        c.append_item(it)
        c.selected = [it]
        c.selectionChanged.emit()
        c.itemsChanged.emit()
        c.eval_all(0.0)
        c.update()
        c.contentChanged.emit()

    # ---------------- 表达式简化 ----------------
    def _has_variables(self, s):
        for v in VARIABLE_NAMES:
            pat = r'(?<![A-Za-z0-9_])' + re.escape(v) + r'(?![A-Za-z0-9_])'
            if re.search(pat, s):
                return True
        return False

    def _try_simplify_expr(self, s):
        """不含变量：直接求值成数字。
        含变量：★保留原样★（不代数化简），
        避免 cos(90)=0 之类把含 Activate1 的项消掉。"""
        if not s: return s
        if self._has_variables(s):
            # ★ 含变量，返回原样，保留完整代数结构
            return s
        # 不含变量 → 尝试求值成常量
        try:
            r = eval(s, {'__builtins__': {}}, dict(EXPR_FUNCS))
            if isinstance(r, (int, float)):
                return _fmt(r)
        except Exception:
            pass
        return simplify_expr(s)

    # ---------------- 输出侧吸附展开 ----------------
    def _expand_bind_expr(self, it, byname, depth=0, visited=None):
        """为绑定到父对象的 it 生成 (pos_expr, vo_expr, rot_expr) 无花括号字符串"""
        if depth > 16: return None
        # ★ 环检测：同一对象在同一路径上出现第二次 → 停止
        if visited is None:
            visited = set()
        oid = id(it)
        if oid in visited:
            return None
        visited = visited | {oid}
        tgt = getattr(it, 'bind_to', u"")
        if not tgt: return None
        parent = byname.get(tgt)
        if parent is None: return None
        pres = self._parent_pos_rot_expr(parent, byname, depth + 1, visited)
        if pres is None: return None
        Ppos, Pvo, Prot = pres
        dxe = self.canvas._eval_bind_field_str(it, 'bind_dx_expr', 'bind_dx')
        dye = self.canvas._eval_bind_field_str(it, 'bind_dy_expr', 'bind_dy')
        bange = self.canvas._eval_bind_field_str(it, 'bind_angle_expr', 'bind_angle')
        cPR = u"cos((%s))" % Prot
        sPR = u"sin((%s))" % Prot
        # 世界偏移 (dx, dy) → 输出坐标增量
        #  pos 增量 = (dx·cos + dy·sin)·20
        #  vo  增量 = (dx·sin - dy·cos)·10
        dpos = u"((%s)*(%s)*20+(%s)*(%s)*20)" % (dxe, cPR, dye, sPR)
        dvo = u"((%s)*(%s)*10-(%s)*(%s)*10)" % (dxe, sPR, dye, cPR)
        pos_expr = u"((%s)+%s)" % (Ppos, dpos)
        vo_expr = u"((%s)+%s)" % (Pvo, dvo)
        rot_expr = u"((%s)+(%s))" % (Prot, bange)
        # ★ 长度保护：展开式超过 6000 字符时直接放弃展开，
        #   让这个对象退回"静态位置"，避免 TMP 标签解析失败
        if (len(pos_expr) + len(vo_expr) + len(rot_expr)) > 6000:
            return None
        #   规则：
        #     属性面板 fx 未勾选 → 不叠加（纯按吸附公式）
        #     fx 勾选且 FT 框为空 → 不叠加
        #     fx 勾选且 FT 框有内容 → 在吸附公式后面"+"上这段内容
        #   举例：吸附到辅助线上滑动，FT 框里填 "Trim"
        #     → 输出 pos = 吸附位置 + Trim
        #     → 输出 vo  = 吸附 voffset + Trim
        #     → 输出 rot = 吸附角度 + Trim
        def _strip_fmt(s):
            """把 {expr;fmt} → (expr, fmt)；{expr} → (expr, '')"""
            e = _unwrap_expr((s or u'').strip())
            if not e:
                return u'', u''
            depth = 0
            in_str = False
            semi = -1
            for i, ch in enumerate(e):
                if ch == '"':
                    in_str = not in_str
                elif in_str:
                    continue
                elif ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
                elif ch == ';' and depth == 0:
                    semi = i
                    break
            if semi >= 0:
                return e[:semi], e[semi:]
            return e, u''

        def _combine(base, extra):
            """base 是无花括号表达式，extra 是用户输入（可能带 {} 或 ;fmt）
            返回无花括号字符串：base+(extra_expr)fmt"""
            e_expr, e_fmt = _strip_fmt(extra)
            if not e_expr:
                return base
            b_expr, b_fmt = _strip_fmt(base)
            # 优先用用户填的 fmt；没有则沿用 base 的
            fmt = e_fmt or b_fmt
            if not b_expr:
                return u"%s%s" % (e_expr, fmt)
            return u"%s+(%s)%s" % (b_expr, e_expr, fmt)

        if getattr(it, 'custom_pos_enabled', False):
            pos_expr = _combine(pos_expr, it.custom_pos_expr)
        if getattr(it, 'custom_vo_enabled', False):
            vo_expr = _combine(vo_expr, it.custom_vo_expr)
        if getattr(it, 'custom_rot_enabled', False):
            rot_expr = _combine(rot_expr, it.custom_rot_expr)
        return pos_expr, vo_expr, rot_expr

    def _parent_pos_rot_expr(self, parent, byname, depth, visited=None):
        if depth > 10: return None
        if visited is None:
            visited = set()
        # ★ 环检测：parent 本身出现在当前路径上 → 停止
        pid = id(parent)
        if pid in visited:
            return None
        # ★ 注意：不要把 parent 加进 visited 再传给 _expand_bind_expr，
        #   因为 _expand_bind_expr 内部会自己把 it 加进 visited。
        #   否则 parent 会立刻被当成"已经在路径上"→返回 None → 展开失败。
        if getattr(parent, 'bind_to', u""):
            sub = self._expand_bind_expr(parent, byname, depth + 1, visited)
            if sub is not None:
                return sub

        if isinstance(parent, RichItem):
            if parent.custom_pos_enabled and parent.custom_pos_expr.strip():
                pe = parent.custom_pos_expr.strip()
                if pe.startswith('{'): pe = pe[1:-1]
            else:
                pe = _fmt(parent.x * POS_PER_WORLD)
            if parent.custom_vo_enabled and parent.custom_vo_expr.strip():
                ve = parent.custom_vo_expr.strip()
                if ve.startswith('{'): ve = ve[1:-1]
            else:
                ve = _fmt(-parent.y * VO_PER_WORLD)
            if parent.custom_rot_enabled and parent.custom_rot_expr.strip():
                re_ = parent.custom_rot_expr.strip()
                if re_.startswith('{'): re_ = re_[1:-1]
            else:
                re_ = _fmt(parent.rotation)
            return pe, ve, re_

        if isinstance(parent, HelperPoint):
            X = self.canvas._helper_field_expr(parent, 'X')
            Y = self.canvas._helper_field_expr(parent, 'Y')
            return (u"(%s)*20" % X, u"-(%s)*10" % Y, u"0")

        if isinstance(parent, HelperLine):
            X1 = self.canvas._helper_field_expr(parent, 'X1')
            Y1 = self.canvas._helper_field_expr(parent, 'Y1')
            X2 = self.canvas._helper_field_expr(parent, 'X2')
            Y2 = self.canvas._helper_field_expr(parent, 'Y2')
            cx = u"((%s)+(%s))/2" % (X1, X2)
            cy = u"((%s)+(%s))/2" % (Y1, Y2)
            pos = u"(%s)*20" % cx
            vo = u"-(%s)*10" % cy
            # 视觉逆时针角 = -atan2(Y2-Y1, X2-X1)
            rot = u"-(atan2((%s)-(%s),(%s)-(%s)))" % (Y2, Y1, X2, X1)
            return pos, vo, rot

        if isinstance(parent, HelperCircle):
            X = self.canvas._helper_field_expr(parent, 'X')
            Y = self.canvas._helper_field_expr(parent, 'Y')
            return (u"(%s)*20" % X, u"-(%s)*10" % Y, u"0")

        return None

    # ---------------- 自定义变量表 ----------------
    def _apply_var_renames(self, s):
        if not s or not self._var_renames: return s
        names = sorted(self._var_renames.keys(), key=len, reverse=True)
        pat = re.compile(r'(?<![A-Za-z0-9_])(' +
                         '|'.join(re.escape(n) for n in names) +
                         r')(?![A-Za-z0-9_])')
        return pat.sub(lambda m: self._var_renames.get(m.group(1), m.group(1)), s)

    def _calc_var_columns(self):
        """决定自定义变量表的列组数（1/2/3），基于自定义函数区域的像素宽度：
        ① 控制面板最小化 / 独立  →  强制 3 列（最高优先）
        ② 宽度 ≥ 600px           →  3 列
        ③ 宽度 ≥ 400px           →  2 列
        ④ 其它                   →  1 列
        """
        # ① 控制面板最小化 / 独立 → 强制 3 列
        if (getattr(self, '_ctrl_minimized', False) or
                getattr(self, '_floating_panel', None) is not None):
            return 3
        # ② ~ ④ 用 var_wrap 宽度（布局完成后准确）
        try:
            w = self._var_wrap.width()
        except Exception:
            w = 0
        # 布局未完成时用 splitter 期望值兜底
        if w <= 0:
            try:
                sizes = self._output_split.sizes()
                w = sizes[1] if len(sizes) > 1 else 0
            except Exception:
                w = 0
        if w >= 600: return 3
        if w >= 400: return 2
        return 1

    def _refresh_var_layout(self):
        cols = self._calc_var_columns()
        if cols != getattr(self, '_var_cols', 1):
            self._set_var_table()

    def eventFilter(self, obj, event):
        try:
            if (obj is self.var_table.viewport()
                    and event.type() == QEvent.Resize
                    and not self._updating_vars):
                self._var_resize_timer.start()
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def _set_var_table(self):
        self._updating_vars = True
        try:
            cols = self._calc_var_columns()
            self._var_cols = cols
            total_cols = cols * 3
            self.var_table.setColumnCount(total_cols)
            hdr = []
            for _ in range(cols):
                hdr += [_T('col_var'), _T('col_expr'), u""]
            self.var_table.setHorizontalHeaderLabels(hdr)
            hh = self.var_table.horizontalHeader()
            for i in range(cols):
                base = i * 3
                hh.setSectionResizeMode(base, QHeaderView.ResizeToContents)
                hh.setSectionResizeMode(base + 1, QHeaderView.Stretch)
                hh.setSectionResizeMode(base + 2, QHeaderView.ResizeToContents)

            n = len(self._cse_defs)
            rows = (n + cols - 1) // cols if cols > 0 else 0
            self.var_table.setRowCount(rows)
            self.var_table.clearContents()

            for idx, (orig_name, expr) in enumerate(self._cse_defs):
                r = idx // cols
                c = (idx % cols) * 3
                shown_name = self._var_renames.get(orig_name, orig_name)
                name_item = QTableWidgetItem(shown_name)
                name_item.setData(Qt.UserRole, orig_name)
                self.var_table.setItem(r, c, name_item)
                shown_expr = self._apply_var_renames(expr)
                expr_item = QTableWidgetItem(shown_expr)
                expr_item.setFlags(expr_item.flags() & ~Qt.ItemIsEditable)
                self.var_table.setItem(r, c + 1, expr_item)
                btn = QPushButton(_T('copy_btn'))
                btn.setFixedHeight(20)
                btn.clicked.connect(
                    lambda checked=False, rr=r, cc=c: self._copy_var_cell(rr, cc))
                self.var_table.setCellWidget(r, c + 2, btn)
        finally:
            self._updating_vars = False

    def _rebuild_output_with_renames(self):
        body = self._apply_var_renames(self._output_raw)
        self.output_edit.setPlainText(body)
        self._update_output_title_bytes(body)

    def _update_output_title_bytes(self, body=None):
        """输出标题栏：`输出： [123 字节]` / `Output: [123 bytes]`"""
        try:
            if body is None:
                body = self.output_edit.toPlainText()
            n_bytes = len(body.encode('utf-8'))
            txt = _L(u"%s [%d 字节]",
                     u"%s [%d bytes]") % (_T('output_title'), n_bytes)
            self.output_title_label.setText(txt)
        except Exception:
            try:
                self.output_title_label.setText(_T('output_title'))
            except Exception:
                pass

    def _on_var_item_changed(self, item):
        if self._updating_vars: return
        col = item.column()
        if col % 3 != 0: return
        row = item.row()
        name_item = self.var_table.item(row, col)
        if name_item is None: return
        orig_name = name_item.data(Qt.UserRole)
        if not orig_name: return
        new_name = item.text().strip()
        cur_name = self._var_renames.get(orig_name, orig_name)
        if new_name == cur_name: return
        # 合法性
        if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', new_name or u''):
            QMessageBox.warning(self, u"重命名",
                                u"非法名（只允许字母数字下划线，不能数字开头）")
            self._updating_vars = True
            item.setText(cur_name)
            self._updating_vars = False
            return
        # 冲突检查（遍历所有列组）
        n_rows = self.var_table.rowCount()
        n_cols = self.var_table.columnCount()
        for i in range(n_rows):
            for j in range(0, n_cols, 3):
                if i == row and j == col: continue
                oi = self.var_table.item(i, j)
                if oi and oi.text() == new_name:
                    QMessageBox.warning(self, u"重命名",
                                        u"名字 [%s] 已存在" % new_name)
                    self._updating_vars = True
                    item.setText(cur_name)
                    self._updating_vars = False
                    return
        self._var_renames[orig_name] = new_name
        # ★ 立即刷新：主输出 / 变量定义块 / 变量表
        self._rebuild_output_with_renames()
        self._set_var_table()
        # ★ 名字变了可能影响前缀冲突判定 → 刷新红框
        try:
            self._validate_var_prefix_style()
        except Exception:
            pass
        # ★ 状态栏提示
        try:
            self.statusBar().showMessage(
                _L(u"已重命名 [%s] → [%s]",
                   u"Renamed [%s] → [%s]") % (orig_name, new_name), 2500)
        except Exception:
            pass

    def _copy_var_cell(self, row, col):
        ei = self.var_table.item(row, col + 1)
        if ei is None: return
        text = ei.text()
        QGuiApplication.clipboard().setText(text)
        self.statusBar().showMessage(
            _L(u"已复制：%s", u"Copied: %s") % text, 2000)

    def refresh_output(self):
        self.canvas.eval_helpers()
        # ★ 关键修复：eval_helpers() 会把所有 _disp_* 重置为 None，
        #   若不在这里重新应用一次绑定，被绑定的辅助对象（圆/线/点）
        #   和字符就会闪回静态位置。
        #   同时这也保证吸附完成后立即显示在正确位置。
        try:
            self.canvas.apply_bindings()
        except Exception:
            pass
        # ★ 调试：打印所有绑定了父对象的字符
        try:
            import sys as _sys
            for _it in self.canvas.items:
                if getattr(_it, 'bind_to', u''):
                    _nm = getattr(_it, 'name', u'?') or u'?'
                    _dxe = getattr(_it, 'bind_dx_expr', u'') or u''
                    _dye = getattr(_it, 'bind_dy_expr', u'') or u''
                    print(u"[bind] %s -> %s | dx=%r dy=%r"
                          % (_nm, _it.bind_to, _dxe[:80], _dye[:80]),
                          file=_sys.stderr)
        except Exception:
            pass
        all_names = self.canvas._all_objects_by_name()
        helper_names = self.canvas.helper_by_name()
        resolve = lambda s: self.canvas._resolve_helper_refs(s, helper_names)

        # 1) 展开绑定 + 简化
        # ★ 两阶段：
        #   阶段一：只用「原始 custom_* 值」展开所有对象（互不影响）
        #   阶段二：全部展开完成后，再统一写回 custom_*
        # 避免展开字符 2 时读到字符 1 被写回的展开式，导致偏移被叠加两次
        saved = []
        expand_results = []
        for it in self.canvas.items:
            if getattr(it, 'bind_to', u""):
                r = self._expand_bind_expr(it, all_names, 0)
                if r is not None:
                    pos, vo, rot = r
                    pos = self._try_simplify_expr(pos)
                    vo = self._try_simplify_expr(vo)
                    rot = self._try_simplify_expr(rot)
                    # ★ 吸附字符的 voffset 末尾加 ;0.00000（限制 5 位小数）
                    if vo and u';' not in vo:
                        vo = vo + u";0.00000"
                    expand_results.append((it, pos, vo, rot))

        # ★ 阶段二：全部展开完，再写回 custom_*
        for it, pos, vo, rot in expand_results:
            saved.append((it,
                          it.custom_pos_expr, it.custom_pos_enabled,
                          it.custom_vo_expr, it.custom_vo_enabled,
                          it.custom_rot_expr, it.custom_rot_enabled))
            it.custom_pos_expr = pos
            it.custom_pos_enabled = True
            it.custom_vo_expr = vo
            it.custom_vo_enabled = True
            it.custom_rot_expr = rot
            it.custom_rot_enabled = True

        # 2) 收集所有字段（resolve 辅助引用后）作为 CSE 输入
        fields = []  # [(it, field_name, 原字符串)]
        texts = []  # 用于 CSE 的内层字符串
        for it in self.canvas.items:
            for fld, en_fld in (
                    ('custom_pos_expr', 'custom_pos_enabled'),
                    ('custom_vo_expr', 'custom_vo_enabled'),
                    ('custom_size_expr', 'custom_size_enabled'),
                    ('custom_rot_expr', 'custom_rot_enabled')):
                if not getattr(it, en_fld, False): continue
                ex = getattr(it, fld, u'') or u''
                s = ex.strip()
                if not s: continue
                if s.startswith('{') and s.endswith('}'): s = s[1:-1]
                s = resolve(s)
                fields.append((it, fld, ex))
                texts.append(s)

        # 3) CSE 提取（受输出栏“自定义变量”按钮控制 + 档位参数）
        defs = []
        cse_on = False
        try:
            cse_on = self.btn_custom_vars.isChecked()
        except Exception:
            cse_on = False
        if not cse_on:
            new_texts = list(texts)
        else:
            try:
                mv, mc, ml, post_max = self._cse_params()
            except Exception:
                mv, mc, ml, post_max = 30, 2, 8, 16
            prefix = self._clean_var_prefix()
            try:
                new_texts, defs = CSEExtractor(
                    prefix=prefix, max_vars=mv,
                    min_count=mc, min_len=ml).extract(texts)
            except Exception:
                import traceback
                traceback.print_exc()
                new_texts = list(texts)
                defs = []
            # ★ 后处理独立 try：即使失败，也保留 CSE 原始结果
            try:
                defs2, new_texts2 = _postprocess_cse_defs(
                    defs, new_texts, max_defs=post_max, prefix=prefix)
                defs, new_texts = defs2, new_texts2
            except TypeError:
                try:
                    defs, new_texts = _postprocess_cse_defs(defs, new_texts)
                except Exception:
                    import traceback
                    traceback.print_exc()
            except Exception:
                import traceback
                traceback.print_exc()

        # （已移除旧的“保底关闭 CSE”检查——它会误伤中/高档位：
        #  只要提取出的定义数 > 15 且引用略稀疏，就会把整个 defs 列表
        #  清空，导致中/高两档永远显示不出任何自定义函数）

        # ★ 调试：把 CSE 结果输出到 stderr（发布时可删掉）
        try:
            import sys as _sys
            print(u"[CSE] defs=%d, new_texts=%d" %
                  (len(defs), len(new_texts)), file=_sys.stderr)
            for i, t in enumerate(new_texts[:5]):
                print(u"  new_texts[%d]=%r" % (i, t[:120]), file=_sys.stderr)
        except Exception:
            pass

        # 4) 临时写回精简后的表达式
        wrote_back = []
        for i, (it, fld, old_expr) in enumerate(fields):
            nt = new_texts[i] if i < len(new_texts) else None
            if nt is None or nt == texts[i]: continue
            setattr(it, fld, u'{' + nt + u'}')
            wrote_back.append((it, fld, old_expr))

        # 5) 生成输出（含自定义变量定义区）
        try:
            s = items_to_rich(self.canvas.items, self.canvas.canvas_w,
                              self.canvas.canvas_h, self.canvas.global_size,
                              self.canvas.glyph_ratio, resolve=resolve)
            self._output_raw = s
            self._cse_defs = list(defs)
            self._rebuild_output_with_renames()
            self._set_var_table()
        finally:
            # 6) 恢复
            for (it, fld, old_expr) in wrote_back:
                setattr(it, fld, old_expr)
            for (it, pe, pe_en, ve, ve_en, re_, re_en) in saved:
                it.custom_pos_expr = pe;
                it.custom_pos_enabled = pe_en
                it.custom_vo_expr = ve;
                it.custom_vo_enabled = ve_en
                it.custom_rot_expr = re_;
                it.custom_rot_enabled = re_en

    def copy_output(self):
        QGuiApplication.clipboard().setText(self.output_edit.toPlainText())
        self.statusBar().showMessage(
            _L(u"已复制到剪贴板", u"Copied to clipboard"), 3000)

    def import_rich(self):
        text, ok = QInputDialog.getMultiLineText(
            self, _T('import_rich_title'),
            _T('import_rich_hint'), self.output_edit.toPlainText())
        if not ok or not text.strip(): return
        items = parse_rich_string(text, self.canvas.canvas_w,
                                  self.canvas.canvas_h, self.canvas.global_size,
                                  self.canvas.glyph_ratio)
        if not items:
            QMessageBox.information(self, _T('hint'), _T('no_element'));
            return
        for it in items:
            it.x, it.y = self.canvas._clamp(it.x, it.y)
        self.canvas.set_items_list(items);
        self.canvas.selected = []
        self.canvas.selectionChanged.emit();
        self.canvas.itemsChanged.emit()
        self.canvas.eval_all(0.0);
        self.canvas.update();
        self.canvas.fit_view()
        self.refresh_output();
        self.charlist.rebuild()

    def export_png(self):
        if not self.canvas.items:
            QMessageBox.information(self, _T('hint'), _T('no_canvas'));
            return
        path, _ = QFileDialog.getSaveFileName(
            self, _T('export_png_title'), "layout.png", _T('export_png_filter'))
        if not path: return
        ppu, ok = QInputDialog.getInt(self, _T('export_res_title'),
                                      _T('export_res_hint'), 800, 100, 4000)
        if not ok: return
        w = int(self.canvas.canvas_w * ppu);
        h = int(self.canvas.canvas_h * ppu)
        img = QImage(w, h, QImage.Format_ARGB32);
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        ox = self.canvas.x_half() * ppu;
        oy = self.canvas.y_half() * ppu
        for it in self.canvas.items:
            if it.hidden: continue
            sx = it.x * ppu + ox;
            sy = it.y * ppu + oy
            font_px = it.disp_size() * FONT_SIZE_UNIT * ppu
            if font_px < 1: continue
            font = it.make_font(font_px)
            fm = QFontMetricsF(font)
            disp = it.display_text()
            if '<' in disp:
                segments = parse_rich_tags(disp, self.canvas.variables)
                char_list = [];
                total_w = 0.0;
                cur_line_w = 0.0;
                max_h = 0.0
                for ch, st in segments:
                    if ch == '\n':
                        if cur_line_w > total_w: total_w = cur_line_w
                        cur_line_w = 0.0;
                        max_h += font_px;
                        continue
                    px = max(1.0, font_px * st['size'])
                    f2 = it.make_font(px, st['bold'], st['italic'])
                    fm_c = QFontMetricsF(f2)
                    if 'space_width_em' in st:
                        cw = st['space_width_em'] * px
                    else:
                        cw = fm_c.horizontalAdvance(ch) * st.get('scale', 1.0)
                        cw += st.get('cspace', 0.0) + st.get('mspace', 0.0)
                    char_list.append((ch, st, f2, fm_c, cw))
                    cur_line_w += cw
                if cur_line_w > total_w: total_w = cur_line_w
                base_fm = QFontMetricsF(font)
                baseline_y = -base_fm.height() / 2.0 + base_fm.ascent()
                baseline_y -= it.disp_up_world(self.canvas.canvas_h) * ppu
                pos_off_px = it.disp_pos_world(self.canvas.canvas_w) * ppu
                p.save()
                p.translate(sx + pos_off_px, sy);
                p.rotate(-it.rotation)
                cursor_x = -total_w / 2.0
                line_off_y = 0.0;
                line_max_h = 0.0
                for ch, st, f2, fm_c, cw in char_list:
                    if fm_c.height() > line_max_h: line_max_h = fm_c.height()
                    draw_x = cursor_x + st['pos']
                    draw_y = baseline_y - st['voffset'] - line_off_y
                    p.save()
                    if abs(st['rotate']) > 0.01:
                        cx = draw_x + cw / 2.0
                        cy = draw_y - base_fm.ascent() / 2.0
                        p.translate(cx, cy);
                        p.rotate(-st['rotate']);
                        p.translate(-cx, -cy)
                    if st.get('mark') is not None:
                        mk = QColor(st['mark'])
                        ma = st.get('mark_alpha', 1.0)
                        if ma < 1.0:
                            a = mk.alphaF() * ma
                            mk.setAlphaF(max(0.0, min(1.0, a)))
                        p.save();
                        p.setPen(Qt.NoPen);
                        p.setBrush(QBrush(mk))
                        p.drawRect(QRectF(draw_x, draw_y - fm_c.ascent(), cw, fm_c.height()))
                        p.restore()
                    p.setFont(f2)
                    col = QColor(st['color']) if st['color'] is not None else QColor(it.color)
                    if st['alpha'] < 1.0:
                        a = col.alphaF() * st['alpha']
                        col.setAlphaF(max(0.0, min(1.0, a)))
                    p.setPen(col)
                    p.drawText(QPointF(draw_x, draw_y), ch)
                    if st.get('underline') or it.underline:
                        p.save();
                        p.setPen(col)
                        y = draw_y + fm_c.descent() * 0.3
                        p.drawLine(QPointF(draw_x, y), QPointF(draw_x + cw, y))
                        p.restore()
                    if st.get('strike') or it.strike:
                        p.save();
                        p.setPen(col)
                        y = draw_y - fm_c.ascent() * 0.35
                        p.drawLine(QPointF(draw_x, y), QPointF(draw_x + cw, y))
                        p.restore()
                    p.restore()
                    cursor_x += cw
                p.restore()
                continue
            tw = fm.horizontalAdvance(disp);
            th = fm.height()
            baseline = -th / 2.0 + fm.ascent()
            baseline -= it.disp_up_world(self.canvas.canvas_h) * ppu
            pos_off_px = it.disp_pos_world(self.canvas.canvas_w) * ppu
            p.save();
            p.translate(sx + pos_off_px, sy);
            p.rotate(-it.rotation)
            p.setFont(font);
            p.setPen(it.color)
            dx0 = -tw / 2.0
            p.drawText(QPointF(dx0, baseline), disp)
            if it.underline:
                p.save();
                p.setPen(it.color)
                y = baseline + fm.descent() * 0.3
                p.drawLine(QPointF(dx0, y), QPointF(dx0 + tw, y))
                p.restore()
            if it.strike:
                p.save();
                p.setPen(it.color)
                y = baseline - fm.ascent() * 0.35
                p.drawLine(QPointF(dx0, y), QPointF(dx0 + tw, y))
                p.restore()
            p.restore()
        p.end()
        if img.save(path):
            self.statusBar().showMessage(u"已导出: " + path, 4000)
        else:
            QMessageBox.warning(self, _T('fail'), _T('img_fail'))

    def _node_to_dict(self, node, hidx=None):
        if node.folder:
            return {"type": "folder", "name": node.name,
                    "children": [self._node_to_dict(c, hidx)
                                 for c in node.children]}
        h = getattr(node, 'helper', None)
        if h is not None:
            idx = hidx.get(id(h), -1) if hidx else -1
            return {"type": "helper_ref", "index": idx}
        return {"type": "item", "item": node.item.to_dict()}

    def _dict_to_node(self, d, hlist=None, depth=0):
        # ★ 深度保护：树嵌套超过 64 层视为异常
        if depth > 64:
            return Node(folder=True, name=u"(深度超限)")
        if d.get("type") == "folder":
            n = Node(folder=True, name=d.get("name", u"文件夹"))
            for c in d.get("children", []):
                ch = self._dict_to_node(c, hlist, depth + 1)
                ch.parent = n;
                n.children.append(ch)
            return n
        if d.get("type") == "helper_ref":
            idx = int(d.get("index", -1))
            h = hlist[idx] if hlist and 0 <= idx < len(hlist) else None
            return Node(folder=False, helper=h)
        return Node(folder=False, item=RichItem.from_dict(d.get("item", {})))

    def _sync_helper_name_seq(self):
        import re as _re
        seq = {'P': 0, 'L': 0, 'C': 0}
        max_char = [0]

        def visit(n):
            h = getattr(n, 'helper', None)
            if h is not None:
                nm = getattr(h, 'name', u"") or u""
                if isinstance(h, HelperPoint):
                    m = _re.match(r'^(?:点|P)(\d+)$', nm)
                    if m: seq['P'] = max(seq['P'], int(m.group(1)))
                elif isinstance(h, HelperLine):
                    m = _re.match(r'^(?:线|L)(\d+)$', nm)
                    if m: seq['L'] = max(seq['L'], int(m.group(1)))
                elif isinstance(h, HelperCircle):
                    m = _re.match(r'^(?:圆|C)(\d+)$', nm)
                    if m: seq['C'] = max(seq['C'], int(m.group(1)))
            # ★ 同步字符序号
            it = getattr(n, 'item', None)
            if it is not None:
                nm = getattr(it, 'name', u"") or u""
                m = _re.match(r'^(?:字符|Char)(\d+)$', nm)
                if m:
                    max_char[0] = max(max_char[0], int(m.group(1)))
            if n.folder:
                for c in n.children: visit(c)

        visit(self.canvas.root)
        self.canvas._helper_name_seq = seq
        # ★ 字符序号只增不减，避免新建字符时和已有名字撞车
        if max_char[0] > self.canvas._char_seq:
            self.canvas._char_seq = max_char[0]

    def save_project(self):
        path, _ = QFileDialog.getSaveFileName(
            self, _T('save_title'), "project.json", _T('save_filter'))
        if not path: return
        pts = self.canvas.helper_points
        lns = self.canvas.helper_lines
        cirs = self.canvas.helper_circles
        hlist = pts + lns + cirs
        hidx = {id(h): i for i, h in enumerate(hlist)}
        data = {
            "version": APP_VERSION,
            "canvas": {"w": self.canvas.canvas_w, "h": self.canvas.canvas_h},
            "global_size": self.canvas.global_size,
            "glyph_ratio": self.canvas.glyph_ratio,
            "snap": {"enabled": self.canvas.snap_enabled,
                     "spacing": self.canvas.snap_spacing},
            "controls": self.get_control_values(),
            "flight_data": self._flight_data,
            "time": self.time_control.value(),
            "tree": self._node_to_dict(self.canvas.root, hidx),
            "helpers": _encode_helpers(pts, lns, cirs),
            # ★ 自定义变量（没有则空列表，兼容老版本）
            "custom_vars": list(self._custom_vars),
            # ★ 压缩程度 / 变量前缀 / 显示开关 / 面板显隐
            "ui_state": self._collect_ui_state(),
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as ex:
            QMessageBox.warning(self, _T('fail'), str(ex));
            return
        self.statusBar().showMessage(_T('save_done'), 3000)

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self, _T('open_title'), "", _T('save_filter'))
        if not path: return
        self._load_project_from_path(path)


# ================================================================ 入口
def _compute_ui_scale(app):
    """计算“额外 UI 放大系数”（0.85 ~ 2.0）。

    · Qt 的 AA_EnableHighDpiScaling 已按系统缩放（125%/150%/200%）自动
      放大字体和控件，这一部分**不重复叠加**。
    · 但如果系统缩放仍是 100%，而屏幕是 2K / 4K，字会非常小 →
      这里手动补一档。
    · 640p / 720p 小屏：保持 1.0（更大反而更挤）。
    """
    try:
        screen = app.primaryScreen()
        if screen is None:
            return 1.0
        dpi = screen.logicalDotsPerInch() or 96.0
        sys_scale = float(dpi) / 96.0
        geo = screen.geometry()
        w = geo.width()
        extra = 1.0
        if w >= 3840 and sys_scale < 1.3:
            extra = 1.5
        elif w >= 2560 and sys_scale < 1.15:
            extra = 1.35
        elif w >= 1920 and sys_scale < 1.0:
            extra = 1.15
        return max(0.85, min(2.0, extra))
    except Exception:
        return 1.0


def main():
    # ★ 崩溃时把 Python 栈写到日志文件
    try:
        import faulthandler, tempfile, os, sys
        _log_path = os.path.join(tempfile.gettempdir(), "tmp_editor_crash.log")
        _log_file = open(_log_path, "w", encoding="utf-8")
        faulthandler.enable(_log_file)
        faulthandler.enable(sys.stderr)
        sys.stderr.write("Crash log: %s\n" % _log_path)
    except Exception:
        pass
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    qt_trans = QTranslator()
    qt_path = QLibraryInfo.location(QLibraryInfo.TranslationsPath)
    qt_trans.load("qt_zh_CN", qt_path)
    app.installTranslator(qt_trans)
    app._qt_trans_zh = qt_trans

    # ★ 根据屏幕分辨率 / 系统缩放计算额外 UI 缩放
    ui_scale = _compute_ui_scale(app)
    base_pt = 9
    pt = max(8, min(20, int(round(base_pt * ui_scale))))
    font = QFont(u"Microsoft YaHei")
    font.setPointSize(pt)
    app.setFont(font)

    win = MainWindow()
    screen = app.primaryScreen().availableGeometry()
    sw, sh = screen.width(), screen.height()

    # ★ 按屏幕档位决定初始占屏比例：
    #   · 高分屏：多占一点，留出控件富余
    #   · 小屏：几乎铺满，避免被挤
    #   · 一般屏：保持原有的 62.5% × 81.25%
    if sw >= 2560 or sh >= 1440:
        w_ratio, h_ratio = 0.70, 0.82
    elif sw < 1366 or sh < 768:
        w_ratio, h_ratio = 0.94, 0.94
    else:
        w_ratio, h_ratio = 0.625, 0.8125

    w = min(int(sw * w_ratio), sw - 40)
    h = min(int(sh * h_ratio), sh - 40)
    win.resize(w, h)
    win.move(screen.left() + (sw - w) // 2,
             screen.top() + (sh - h) // 2)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()