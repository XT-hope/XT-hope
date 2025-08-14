import re
import sys
import csv
from pathlib import Path
from typing import List, Tuple, Optional, Dict

Heading = Dict[str, Optional[str]]

HEADING_RE = re.compile(r"^\s*(?P<num>\d+(?:\.\d+)+)\s+(?P<title>.*?)(?:【(?P<id>[^】]+)】)?\s*$")
BRANCH_HEADER_RE = re.compile(r"^\s*\d+\.\s*(以下条件同时满足|以下条件满足其一)\s*[:：]?\s*$")
SUBITEM_RE = re.compile(r"^\s{2,}\d+\.\s*(.+)$")
_EXPL_HEAD_RE = r"(?P<head>\{[^{}]+\}\s*(?:==|>=|<=|!=|=|>|<|＞＝|＜＝|≥|≤|≠|＞|＜|＝)\s*)"

def strip_braces(text: str) -> str:
    # 仅移除花括号字符，保留内部内容
    return text.replace("{", "").replace("}", "")

def strip_brackets_pair(text: str) -> str:
    # 完全移除中文方括号部分【...】
    return re.sub(r"【[^】]*】", "", text)

def strip_colon(text: str) -> str:
    return text.replace("：", ":")

def normalize_text(text: str) -> str:
    text = text.strip()
    text = strip_brackets_pair(text)
    text = strip_braces(text)
    # 规范化内部空白字符
    text = re.sub(r"\s+", " ", text)
    text = strip_colon(text)
    return text.strip()


def is_heading(line: str) -> Optional[Heading]:
    m = HEADING_RE.match(line.strip())
    if not m:
        return None
    num = m.group("num")
    title = m.group("title").strip()
    req_id = m.group("id")
    return {"num": num, "title": title, "id": req_id}


def heading_level(heading_num: str) -> int:
    return len(heading_num.split("."))


def split_conditions_by_or(cond: str) -> List[str]:
    # 按完整单词 'or'（不区分大小写）并基于词边界拆分
    parts = re.split(r"\bor\b", cond, flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()]

def _normalize_explanation_suffix_once(text: str) -> str:
    s = text

    # 辅助：在前导数字与识别的单位之间插入空格
    # 例如：135kph -> 135 kph；105KPH -> 105 KPH；500ms（作为数值时保留）
    unit_compact_value_re = re.compile(
        r"^(?P<num>[-+]?\d+(?:\.\d+)?)\s*(?P<unit>kph|kmh|kmph|mph|rpm|kpa|pa|bar|hz|khz|mhz|ghz|v|a|ma|ua|mv|g|kg|n)$",
        re.IGNORECASE,
    )

    def insert_space_number_unit(val: str) -> str:
        m = unit_compact_value_re.match(val)
        if not m:
            return val
        return f"{m.group('num')} {m.group('unit')}"

    # 0) 处理操作符之前、紧随花括号信号名之后的注释。
    #    示例：{X}(描述) == 0x1(Active) -> {X} == 0x1: Active-描述
    #    示例：{X}(描述) = 0x0 -> {X} = 0x0: 描述
    def repl_sig_annot_full(m: re.Match) -> str:
        braced = m.group("braced")
        op = m.group("op")
        val = insert_space_number_unit(m.group("val"))
        sig_expl = (m.group("sigexpl") or m.group("sigexpl2") or "").strip()
        val_expl = (m.group("valexpl") or m.group("valexpl2") or "").strip()
        # 组合说明
        if val_expl and sig_expl:
            expl = f"{val_expl}-{sig_expl}"
        else:
            expl = val_expl or sig_expl
        return f"{braced} {op} {val}: {expl}" if expl else f"{braced} {op} {val}"

    pattern_sig_annot_full = re.compile(
        r"(?P<braced>\{[^{}]+\})\s*(?:\(\s*(?P<sigexpl>[^()（）:]+?)\s*\)|（\s*(?P<sigexpl2>[^()（）:]+?)\s*）)\s*"
        r"(?P<op>==|>=|<=|!=|=|>|<|＞＝|＜＝|≥|≤|≠|＞|＜|＝)\s*"
        r"(?P<val>[^\s:()（）]+)\s*"
        r"(?:\(\s*(?P<valexpl>[^()（）:]+?)\s*\)|（\s*(?P<valexpl2>[^()（）:]+?)\s*）)?"
        r"(?=(?:\s*(?:&&|\|\|)|\s*$))"
    )
    s_new = pattern_sig_annot_full.sub(repl_sig_annot_full, s)

    # 降级路径：仅在操作符前存在信号注释、且无取值说明时
    def repl_sig_annot_simple(m: re.Match) -> str:
        braced = m.group("braced")
        op = m.group("op")
        val = insert_space_number_unit(m.group("val"))
        sig_expl = (m.group("sigexpl") or m.group("sigexpl2") or "").strip()
        return f"{braced} {op} {val}: {sig_expl}" if sig_expl else f"{braced} {op} {val}"

    pattern_sig_annot_simple = re.compile(
        r"(?P<braced>\{[^{}]+\})\s*(?:\(\s*(?P<sigexpl>[^()（）:]+?)\s*\)|（\s*(?P<sigexpl2>[^()（）:]+?)\s*）)\s*"
        r"(?P<op>==|>=|<=|!=|=|>|<|＞＝|＜＝|≥|≤|≠|＞|＜|＝)\s*"
        r"(?P<val>[^\s:()（）]+)"
        r"(?=(?:\s*(?:&&|\|\|)|\s*$))"
    )
    s_new = pattern_sig_annot_simple.sub(repl_sig_annot_simple, s_new)

    # 1) 括号说明：{X} == 0x0 (Unavailable) / （Unavailable） -> {X} == 0x0: Unavailable
    def repl_paren(m: re.Match) -> str:
        head = m.group("head")
        val = insert_space_number_unit(m.group("val"))
        expl = m.group("expl").strip()
        # 仅当说明显式包含布尔运算符时跳过，避免破坏表达式
        if "&&" in expl or "||" in expl:
            return m.group(0)
        return f"{head}{val}: {expl}"

    pattern_paren = re.compile(
        _EXPL_HEAD_RE + r"(?P<val>[^\s:()（）]+)\s*(?:\(|（)\s*(?P<expl>[^()（）:]+?)\s*(?:\)|）)"
    )
    s_new = pattern_paren.sub(repl_paren, s_new)

    # 2) 无空格追加说明：{X} == 0x0Unavailable -> {X} == 0x0: Unavailable
    def repl_nospace(m: re.Match) -> str:
        head = m.group("head")
        val = insert_space_number_unit(m.group("val"))
        expl = m.group("expl").strip()
        # 保护：若紧跟的字符为 '/'，很可能是 3m/s² 这类计量单位；跳过
        s_full: str = m.string
        if m.end() < len(s_full):
            next_char = s_full[m.end()]
            if next_char in "/²^":
                return m.group(0)
        return f"{head}{val}: {expl}"

    pattern_nospace = re.compile(
        _EXPL_HEAD_RE
        + r"(?P<val>(?:0x[0-9A-Fa-f]+?(?=(?:[A-Z][a-z])|[^0-9A-Fa-f]))|(?:[-+]?\d+(?:\.[\d]+)?%?)(?![xX][0-9A-Fa-f]))"
        + r"(?P<expl>(?:[A-Za-z][A-Za-z0-9_\-]*|[\u4e00-\u9fa5][\u4e00-\u9fa5A-Za-z0-9_\-]*)(?:\s+[A-Za-z\u4e00-\u9fa5][^:()（）]*)?)"
    )
    s_new = pattern_nospace.sub(repl_nospace, s_new)

    # 3) 逗号/中文逗号后的说明：
    #    {X} == 1，debounce 500ms -> {X} == 1: debounce 500ms
    #    {X} = 0x1: Active，debounce 1000ms -> {X} = 0x1: Active: debounce 1000ms
    def repl_comma(m: re.Match) -> str:
        head = m.group("head")
        val = insert_space_number_unit(m.group("val").strip())
        expl = m.group("expl").strip()
        if not expl:
            return m.group(0)
        # 如果值已包含冒号（例如 "0x1: Active"），
        # 则将逗号后的内容视为外部注释，不进行转换
        if ":" in val or "：" in val:
            return m.group(0)
        return f"{head}{val}: {expl}"

    pattern_comma = re.compile(
        _EXPL_HEAD_RE + r"(?P<val>[^,，:：()（）\"]+?)\s*[，,]\s*(?P<expl>[^()（）\"]*?)\s*(?=(?:&&|\|\||$))"
    )
    s_new = pattern_comma.sub(repl_comma, s_new)

    # 处理值后的引号说明：
    #   {X} = 0x3C "请控制车辆，注意环境变化" -> {X} = 0x3C:"请控制车辆，注意环境变化"
    def repl_quoted(m: re.Match) -> str:
        head = m.group("head")
        val = insert_space_number_unit(m.group("val"))
        expl = (m.group("expl1") or m.group("expl2") or "").strip()
        return f"{head}{val}:\"{expl}\""

    pattern_quoted = re.compile(
        _EXPL_HEAD_RE
        + r"(?P<val>[^\s:()（）\"]+)\s*(?:\"(?P<expl1>[^\"]+)\"|“(?P<expl2>[^”]+)”)"
    )
    s_new = pattern_quoted.sub(repl_quoted, s_new)

    # 3) 用空格分隔的说明（确保在 &&、|| 或行尾之前结束）：
    #    {X} == 0x0 Unavailable -> {X} == 0x0: Unavailable
    #    防止将十六进制序列误拆分（例如，0x1Enabled）
    def repl_space(m: re.Match) -> str:
        head = m.group("head")
        val = insert_space_number_unit(m.group("val"))
        expl = m.group("expl").strip()
        # 对非说明性的常见关键字进行保护
        if expl.lower() in {"and", "or"}:
            return m.group(0)
        return f"{head}{val}: {expl}"

    pattern_space = re.compile(
        _EXPL_HEAD_RE
        + r"(?P<val>[^\s:()（）]+)\s+(?P<expl>[A-Za-z\u4e00-\u9fa5][^:()（）]*?)\s*(?=(?:&&|\|\||$))"
    )
    s_new = pattern_space.sub(repl_space, s_new)

    return s_new

def normalize_explanation_suffix(text: str) -> str:
    # 单次遍历即可，避免出现如 '0x0' -> '0: x0' 的二次处理
    return _normalize_explanation_suffix_once(text)

def handle_parse_conditions_item(item: str) -> str:
    """仅在顶层展开以斜杠分隔的备选项，并规范 EV/DM 的顺序。

    - 顶层斜杠："{X}=A/B" -> "({X}=A || {X}=B)"
    - 当斜杠位于括号内时不拆分："=0x3(Resume/+)" 保持不变
    - 在构造比较表达式时，将 "EV:10%" 规范为 "10%:EV"，其它 label:value -> value:label 同理
    """
        # 若在花括号信号比较之前存在描述性文本，则在两者之间插入 ':'
    def insert_colon_before_signal_if_prefixed(text: str) -> str:
        m = re.search(r"(?P<prefix>.*?\S)\s+(?=\{[^{}]+\}\s*(?:==|>=|<=|!=|=|>|<))", text)
        if not m:
            return text
        prefix = m.group("prefix")
        last_char = prefix[-1]
        # 若前缀已以冒号结尾，或前方紧跟分组/布尔标记，则跳过
        if last_char in (':', '：', '(', '（', '[', '【'):
            return text
        if prefix.endswith('&&') or prefix.endswith('||'):
            return text
        return prefix + ':' + text[m.end():].lstrip()

    item = insert_colon_before_signal_if_prefixed(item)

    # 仅当存在显式布尔运算符时才包裹，以保留分组关系
    needs_wrap = any(tok in item for tok in ("&&", "||", "&"))

    def is_unit_slash_at(s: str, idx: int) -> bool:
        """启发式判断 s[idx] 位置的 '/' 是否属于计量单位（如 'm/s' 或 'km/h'）。

        判定条件：
        - '/' 两侧的紧邻非空白字符均为字母（或 '°'、'µ'）。
        - 在左侧单位标记之前（忽略空格）紧邻处存在数字或 '.'，强烈暗示为计量单位。
        """
        if idx <= 0 or idx >= len(s) - 1:
            return False
        # 定位 '/' 周围最近的非空白字符
        li = idx - 1
        while li >= 0 and s[li].isspace():
            li -= 1
        ri = idx + 1
        while ri < len(s) and s[ri].isspace():
            ri += 1
        if li < 0 or ri >= len(s):
            return False
        left_ch = s[li]
        right_ch = s[ri]
        def is_unit_char(ch: str) -> bool:
            return ch.isalpha() or ch in "°µ"
        if not (is_unit_char(left_ch) and is_unit_char(right_ch)):
            return False
        # 向左回溯至左侧单位标记的起始
        lstart = li
        while lstart >= 0 and is_unit_char(s[lstart]):
            lstart -= 1
        # 单位标记之前的上一个有效字符
        pj = lstart
        while pj >= 0 and s[pj].isspace():
            pj -= 1
        if pj >= 0 and (s[pj].isdigit() or s[pj] in ".°"):
            return True
        return False

    def find_top_level_slash(s: str, cutoff_idx: Optional[int] = None) -> int:
        depth = 0
        for idx, ch in enumerate(s):
            if ch in ('(', '（'):
                depth += 1
            elif ch in (')', '）'):
                depth = max(depth - 1, 0)
            elif ch == '/' and depth == 0:
                # 跳过作为计量单位一部分的斜杠，例如 m/s
                if is_unit_slash_at(s, idx):
                    continue
                return idx
        return -1
    
    def split_by_top_level_slash(s: str) -> List[str]:
        """在忽略括号层级的前提下，按顶层 '/' 拆分字符串；跳过空片段。
        例："A /B/ C(Keep/It) / D" -> ["A", "B", "C(Keep/It)", "D"]
        """
        parts: List[str] = []
        buf: List[str] = []
        depth = 0
        for idx, ch in enumerate(s):
            if ch in ('(', '（'):
                depth += 1
                buf.append(ch)
            elif ch in (')', '）'):
                depth = max(depth - 1, 0)
                buf.append(ch)
            elif ch == '/' and depth == 0:
                # 若该斜杠属于计量单位（如 m/s），则保留为文本
                if is_unit_slash_at(s, idx):
                    buf.append(ch)
                    continue
                seg = ''.join(buf).strip()
                if seg:
                    parts.append(seg)
                buf = []
            else:
                buf.append(ch)
        tail = ''.join(buf).strip()
        if tail:
            parts.append(tail)
        return parts

    def normalize_label_value(expr: str) -> str:
        """将 'LABEL:VALUE' 规范为 'VALUE:LABEL'（当 LABEL 为单词且冒号为 ASCII 时）。
        其他内容保持不变。
        """
        m = re.match(r"^\s*([A-Za-z][A-Za-z0-9_]*)\s*:\s*([^:]+?)\s*$", expr)
        if m:
            label = m.group(1).strip()
            value = m.group(2).strip()
            return f"{value}:{label}"
        return expr.strip()
    
    def find_op_rhs_start(s: str) -> Optional[int]:
        m = re.search(r"\{[^{}]+\}\s*(==|>=|<=|!=|=|>|<)", s)
        return m.end() if m else None

    def find_first_top_level_ascii_colon_from(s: str, start: int) -> int:
        depth = 0
        for idx in range(start, len(s)):
            ch = s[idx]
            if ch in ('(', '（'):
                depth += 1
            elif ch in (')', '）'):
                depth = max(depth - 1, 0)
            elif ch == ':' and depth == 0:
                return idx
        return -1
    
    op_rhs_idx = find_op_rhs_start(item)
    slash_idx = find_top_level_slash(item)
    if slash_idx != -1:
        pre = item[:slash_idx].strip()
        post = item[slash_idx + 1:].strip()

        # 从左侧（'/' 之前）提取头部与关系符
        ops = ["==", ">=", "<=", "!=", ">", "<", "="]
        header = None
        op_found = None
        for op in ops:
            if op in pre:
                header = pre.split(op, 1)[0].strip()
                op_found = op
                break

        # 仅对显式的信号/数值比较（如 {X} = A/B）展开斜杠备选项
        if header and op_found and re.match(r"^\{[^{}]+\}$", header):
            left_val_raw = pre.split(op_found, 1)[1].strip()
            # 收集所有右侧候选值：包含左值，并将余下部分按顶层 '/' 拆分
            rhs_alternatives_raw = [left_val_raw] + split_by_top_level_slash(post)
            # 规范 label:value 的顺序
            rhs_alternatives = [normalize_label_value(v) for v in rhs_alternatives_raw if v.strip()]
            # 为所有候选值构建 OR 表达式
            exprs = [f"{header} {op_found} {val}" for val in rhs_alternatives]
            out = f"({' || '.join(exprs)})"
            return normalize_explanation_suffix(out)

    out = f"({item})" if needs_wrap else item
    return normalize_explanation_suffix(out)

def parse_conditions(lines: List[str], start_idx: int) -> Tuple[str, int]:
    """
    解析 IF 与 THEN 之间的条件。
    返回值：(conditions_str, 下一步应位于 THEN 行的位置下标)
    """
    def parse_nested(i: int, top_agg: Optional[str]) -> Tuple[str, int]:
        branches: List[str] = []
        while i < len(lines):
            line = lines[i].rstrip("\n")
            if line.strip().startswith("THEN"):
                break
            # 新的分支标题，如 "  1. 以下条件同时满足：" 或 "  2. ..."
            if BRANCH_HEADER_RE.match(line):
                # 依据标题短语确定分支聚合符
                phrase = "以下条件同时满足" if "以下条件同时满足" in line else "以下条件满足其一"
                branch_agg = "&&" if phrase == "以下条件同时满足" else "||"
                i += 1
                # 收集子项：既接受更深缩进的有序编号行，也接受纯缩进行
                subitems: List[str] = []
                while i < len(lines):
                    sub_line = lines[i].rstrip("\n")
                    if sub_line.strip().startswith("THEN"):
                        break
                    # 遇到另一分支标题 -> 结束当前分支
                    if BRANCH_HEADER_RE.match(sub_line):
                        break
                    # 接受以 N. 开头的行，或至少两个空格缩进的内容行
                    m_sub = SUBITEM_RE.match(sub_line)
                    if not m_sub:
                        # 将缩进的非空行视为当前分支块的一部分（例如无编号）
                        if re.match(r"^\s{2,}\S", sub_line):
                            item = sub_line.strip()
                            parts = split_conditions_by_or(item)
                            if len(parts) > 1:
                                handled = [handle_parse_conditions_item(p) for p in parts]
                                subitems.append(" || ".join(handled))
                            else:
                                subitems.append(handle_parse_conditions_item(item))
                            i += 1
                            continue
                        # 分支内的空行
                        if not sub_line.strip():
                            i += 1
                            continue
                        # 非缩进的普通行 -> 分支结束
                        break
                    item = m_sub.group(1).strip()
                    parts = split_conditions_by_or(item)
                    if len(parts) > 1:
                        handled = [handle_parse_conditions_item(p) for p in parts]
                        subitems.append(" || ".join(handled))
                    else:
                        subitems.append(handle_parse_conditions_item(item))
                    i += 1
                # 按分支聚合符连接子项，并加上括号
                if subitems:
                    branches.append(f"({f' {branch_agg} '.join(subitems)})")
                else:
                    branches.append("")
                continue
            # 非分支标题行
            if not line.strip():
                i += 1
                continue
            # 如果遇到明显结束 IF 块的内容则停止
            if HEADING_RE.match(line.strip()):
                break
            if re.match(r"^\s*[CB]平台", line) or re.match(r"^\s*\{?FSM_index", line):
                break
            # 若遇到顶层聚合符下的普通编号条件（回退策略）
            m_plain = re.match(r"^\s*\d+\.\s*(.*)$", line)
            if m_plain:
                item = m_plain.group(1).strip()
                parts = split_conditions_by_or(item)
                if len(parts) > 1:
                    handled = [handle_parse_conditions_item(p) for p in parts]
                    branches.append("(" + " || ".join(handled) + ")")
                else:
                    branches.append(handle_parse_conditions_item(item))
                i += 1
                continue
            # 否则停止以避免死循环
            break
        # 组装顶层连接符
        joiner = top_agg if top_agg else " && "
        cond = f" {joiner} ".join([b for b in branches if b])
        return cond, i
    
    aggregator: Optional[str] = None  # '&&' 或 '||'
    collected: List[str] = []

    i = start_idx

        # 预览是否存在嵌套的顶层指引
    # 跳过空行
    j = i
    while j < len(lines) and not lines[j].strip():
        j += 1
    if j < len(lines) and ("以下条件同时满足" in lines[j] or "以下条件满足其一" in lines[j]):
        aggregator = "&&" if "以下条件同时满足" in lines[j] else "||"
        j += 1
        # 如果下一个有效行是分支标题，则使用嵌套解析
        k = j
        while k < len(lines) and not lines[k].strip():
            k += 1
        if k < len(lines) and BRANCH_HEADER_RE.match(lines[k]):
            cond_str, idx_after = parse_nested(k, aggregator)
            # 前进到 THEN（或嵌套解析结束的位置）
            # 将 i 移动到 parse_results 期望的 THEN 所在位置
            # 继续扫描直至遇到 THEN 或终止条件
            mpos = idx_after
            while mpos < len(lines) and not lines[mpos].strip().startswith("THEN"):
                if lines[mpos].strip() == "IF":
                    break
                if HEADING_RE.match(lines[mpos].strip()):
                    break
                mpos += 1
            return cond_str, mpos
        # 否则回退为使用已设置聚合符的扁平解析
        aggregator_set = aggregator
        i = j
    else:
        aggregator_set = None
    
    while i < len(lines):
        line = lines[i].rstrip("\n")
        if not line.strip():
            i += 1
            continue
        # 遇到 THEN 则停止
        if line.strip().startswith("THEN"):
            break

        if BRANCH_HEADER_RE.match(line):
            phrase = "以下条件同时满足" if "以下条件同时满足" in line else "以下条件满足其一"
            subgroup_agg = "&&" if phrase == "以下条件同时满足" else "||"
            i += 1
            subitems: List[str] = []
            while i < len(lines):
                sub_line = lines[i].rstrip("\n")
                if sub_line.strip().startswith("THEN"):
                    break
                if BRANCH_HEADER_RE.match(sub_line):
                    break
                m_sub = SUBITEM_RE.match(sub_line)
                if not m_sub:
                    if re.match(r"^\s{2,}\S", sub_line):
                        item = sub_line.strip()
                        parts = split_conditions_by_or(item)
                        if len(parts) > 1:
                            handled = [handle_parse_conditions_item(p) for p in parts]
                            subitems.append(" || ".join(handled))
                        else:
                            subitems.append(handle_parse_conditions_item(item))
                        i += 1
                        continue
                    if not sub_line.strip():
                        i += 1
                        continue
                    break
                item = m_sub.group(1).strip()
                parts = split_conditions_by_or(item)
                if len(parts) > 1:
                    handled = [handle_parse_conditions_item(p) for p in parts]
                    subitems.append(" || ".join(handled))
                else:
                    subitems.append(handle_parse_conditions_item(item))
                i += 1
            if subitems:
                collected.append(f"({f' {subgroup_agg} '.join(subitems)})")
                #print(f"({f' {subgroup_agg} '.join(subitems)})")
                continue

        
        # 识别指引行
        if "以下条件同时满足" in line:
            aggregator_set = "&&"
            i += 1
            continue
        if "以下条件满足其一" in line:
            # 不在此处切换全局聚合符；独立的指引行应当由随后的子组跟随
            # 若该行未带编号，尝试将其后续缩进行解析为一个子组
            lookahead = i + 1
            subitems: List[str] = []
            while lookahead < len(lines):
                la_line = lines[lookahead].rstrip("\n")
                if la_line.strip().startswith("THEN"):
                    break
                if BRANCH_HEADER_RE.match(la_line):
                    break
                m_la = SUBITEM_RE.match(la_line)
                if not m_la:
                    if re.match(r"^\s{2,}\S", la_line):
                        item = la_line.strip()
                        parts = split_conditions_by_or(item)
                        subitems.append(" || ".join(handle_parse_conditions_item(p) for p in parts) if len(parts) > 1 else handle_parse_conditions_item(item))
                        lookahead += 1
                        continue
                    if not la_line.strip():
                        lookahead += 1
                        continue
                    break
                item = m_la.group(1).strip()
                parts = split_conditions_by_or(item)
                subitems.append(" || ".join(handle_parse_conditions_item(p) for p in parts) if len(parts) > 1 else handle_parse_conditions_item(item))
                lookahead += 1
            if subitems:
                collected.append(f"({f' || '.join(subitems)})")
                #print(f"({f' || '.join(subitems)})")
                i = lookahead
                continue
            # 若未找到子项，则出于安全考虑将聚合符设为 OR
            aggregator_set = "||"
            i += 1
            continue
        # 去除编号如 '1. ' 或 '2. '
        m = re.match(r"^\s*\d+\.\s*(.*)$", line)
        if m:
            item = m.group(1).strip()
        else:
            # 普通条件行
            item = line.strip()

        if item:
            # 按独立的 'or' 拆分
            parts = split_conditions_by_or(item)
            if len(parts) > 1:
                handled = [handle_parse_conditions_item(p) for p in parts]
                collected.append(" || ".join(handled))
            else:
                collected.append(handle_parse_conditions_item(item))
        i += 1

    # 连接已收集的条件
    if not collected:
        cond_str = ""
    else:
        joiner = aggregator_set if aggregator_set else " && "
        cond_str = joiner.join(collected)

    return cond_str, i  # i 位于 THEN 行的下标


def parse_results(lines: List[str], start_idx: int) -> Tuple[str, int]:
    """
    解析 THEN 及可选的 ELSE 下的预期结果，直到遇到下一个类标题行或空白段分隔。
    返回：(results_str, 该块结束后的下一行下标)
    """
    results_then: List[str] = []
    results_else: List[str] = []

    i = start_idx

    # 当前解析区段：'THEN' 或 'ELSE'
    current = None

    def should_stop(line: str) -> bool:
        if not line.strip():
            return False  # 允许稀疏的空行
        if HEADING_RE.match(line.strip()):
            return True
        if re.match(r"^\s*[CB]平台", line):
            return True
        if re.match(r"^\s*\{?FSM_index", line):
            return True
        # 遇到新的 IF，说明另一个块开始
        if line.strip() == "IF":
            return True
        return False

    while i < len(lines):
        line = lines[i].rstrip("\n")

        if should_stop(line):
            break

        if line.strip().startswith("THEN"):
            current = "THEN"
            i += 1
            continue
        if line.strip().startswith("ELSE"):
            current = "ELSE"
            i += 1
            continue

        if not line.strip():
            i += 1
            continue

        # 捕获有意义的内容行
        m = re.match(r"^\s*\d+\.\s*(.*)$", line)
        item = m.group(1).strip() if m else line.strip()
        item = normalize_explanation_suffix(item)

        if current == "ELSE":
            results_else.append(item)
        else:
            # 若未显式设置当前区段，默认归入 THEN
            results_then.append(item)
        i += 1

    # 组装结果字符串
    def join_items(items: List[str]) -> str:
        items = [s for s in (x.strip() for x in items) if s]
        return " && ".join(items)

    then_str = join_items(results_then)
    else_str = join_items(results_else)

    if then_str and else_str:
        out = f"THEN: {then_str} || ELSE: {else_str}"
    else:
        out = then_str or else_str

    return out, i


def extract_rows(text: str) -> List[Tuple[str, str, str, str, str]]:
    lines = text.splitlines()

    # 按层级跟踪当前标题栈
    # 映射：层级 -> 标题对象
    stack: Dict[int, Heading] = {}

    rows: List[Tuple[str, str, str, str, str]] = []

    i = 0
    while i < len(lines):
        line = lines[i].rstrip("\n")

        # 更新标题栈
        h = is_heading(line)
        if h:
            level = heading_level(h["num"])  # type: ignore[arg-type]
            # 修剪更深层级
            for k in list(stack.keys()):
                if k >= level:
                    stack.pop(k, None)
            stack[level] = h
            i += 1
            continue

        # 识别 IF 块
        if line.strip() == "IF":
            # 确定最近的、带 ID 的上层标题（用于 需求ID 和 测试点）
            nearest_with_id: Optional[Heading] = None
            deepest_level = max(stack.keys()) if stack else None
            if deepest_level is not None:
                for lev in range(deepest_level, 0, -1):
                    head = stack.get(lev)
                    if head and head.get("id"):
                        nearest_with_id = head
                        break

            # 确定用于 HIL初始条件 的三级标题
            third_level_heading = stack.get(3)

            # 解析 IF 与 THEN 之间的条件
            cond_str, idx_at_then = parse_conditions(lines, i + 1)

            # 解析 THEN/ELSE 下的结果
            results_str, next_idx = parse_results(lines, idx_at_then)

            # 构建字段
            req_id = nearest_with_id.get("id") if nearest_with_id else ""
            # 测试点：编号 + 空格 + 去除【】与 {} 的标题文本
            if nearest_with_id:
                test_point = f"{nearest_with_id['num']} {nearest_with_id['title']}"
            else:
                # 回退：使用最深层但无 ID 的标题
                if deepest_level is not None and stack.get(deepest_level):
                    h2 = stack[deepest_level]
                    test_point = f"{h2['num']} {h2['title']}"
                else:
                    test_point = ""

            # HIL初始条件：三级标题的文本内容（不含 ID 部分）
            if third_level_heading:
                hil_init = f"{third_level_heading['num']} {third_level_heading['title']}"
                # 示例期望仅保留文本，不要编号；因此仅保留标题文本
                hil_init = third_level_heading['title']  # type: ignore[index]
            else:
                hil_init = ""

            if "->" in hil_init:
                hil_init = hil_init.split("->")[0]
            # print(hil_init)

            # 按规则清理字段
            req_id = (req_id or "").strip()
            test_point = normalize_text(test_point)
            # 测试点仅保留编号与标题（不含任何括注）；normalize_text 已移除括注

            hil_init = normalize_text(hil_init)
            cond_str = normalize_text(cond_str)
            results_str = normalize_text(results_str)
            if "from" in results_str:
                results_str_head=results_str.split("from")[0].strip()
                from_message=results_str.split("from")[1].split("to")[0].strip()
                to_message=results_str.split("from")[1].split("to")[1].strip()
                results_str=f"{results_str_head} = {to_message}"
                hil_init=f"{hil_init} : {results_str_head} = {from_message}"
            else:
                hil_init=f"{hil_init} : {results_str}"

            # 如果 
            
            cond_strs=[]
            if "Either&&" in cond_str:
                cond_strs=cond_str.split("Either&&")[1].split("&&OR&&")
                
            if "=" in hil_init:
                hil_init_value=hil_init.split("=")[1].strip()
                hil_init_value_head=hil_init.split("=")[0].strip()
                if "/" in hil_init_value:
                    hil_init_values=hil_init_value.split("/")
                    for i in range(len(hil_init_values)):
                        value=f"{hil_init_value_head} = {hil_init_values[i]}"
                        if cond_strs:
                            for cond_str in cond_strs:
                                rows.append((req_id, test_point.split(" ", 1)[1] if " " in test_point else test_point,
                                value, cond_str, results_str))
                        else:
                            rows.append((req_id, test_point.split(" ", 1)[1] if " " in test_point else test_point,
                                value, cond_str, results_str))
                # 另外，测试点是否应去掉前导编号？示例保留编号，因此保持原样。
                # HIL初始条件示例仅要标题文本（不带编号），上面已处理。
                else:
                    if cond_strs:
                        for cond_str in cond_strs:
                            rows.append((req_id, test_point.split(" ", 1)[1] if " " in test_point else test_point,
                                hil_init, cond_str, results_str))
                    else:
                        rows.append((req_id, test_point.split(" ", 1)[1] if " " in test_point else test_point,
                            hil_init, cond_str, results_str))
            else:
                if cond_strs:
                    for cond_str in cond_strs:
                        rows.append((req_id, test_point.split(" ", 1)[1] if " " in test_point else test_point,
                            hil_init, cond_str, results_str))
                else:
                    rows.append((req_id, test_point.split(" ", 1)[1] if " " in test_point else test_point,
                        hil_init, cond_str, results_str))

            i = next_idx
            continue

        i += 1

    return rows


def write_csv(rows: List[Tuple[str, str, str, str, str]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["需求ID", "测试点", "HIL初始条件", "HIL测试步骤", "HIL预期结果"])
        for r in rows:
            writer.writerow(list(r))


def main():
    if len(sys.argv) < 3:
        print("用法: python parse_md_file.py <输入txt路径> <输出csv路径>")
        sys.exit(1)

    in_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])

    if not in_path.exists():
        print(f"输入文件不存在: {in_path}")
        sys.exit(2)

    text = in_path.read_text(encoding="utf-8")
    rows = extract_rows(text)
    write_csv(rows, out_path)
    print(f"已生成: {out_path} ({len(rows)} 条)")


if __name__ == "__main__":
    main()