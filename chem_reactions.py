#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chem_reactions.py

Простой движок для генерации и балансировки химических реакций.

Возможности:
- Разбор формул (поддержка скобок и индексов)
- Балансировка уравнений (рациональные коэффициенты сводятся к целым)
- Генерация возможных типов реакций: нейтрализация (кислота+основание), обмен (двойной обмен),
  замещение (замена металлом по ряду активности), горение (углеводород + O2 -> CO2 + H2O)
- Учитываются базовые правила: таблица растворимости (упрощённая), ряд напряжений металлов

Ограничения:
- Это учебный инструмент — не покрывает все возможные химические случаи и исключения.

API:
- generate_reactions(reactants: list[str]) -> list[dict]
    Возвращает список вариантов реакций. Каждый вариант содержит:
    - "type": тип реакции (string)
    - "reactants": list[str]
    - "products": list[str]
    - "balanced": (reactant_coeffs, product_coeffs)
    - "steps": текстовое объяснение

Пример использования внизу файла (если запущен как __main__).
"""

from __future__ import annotations
from dataclasses import dataclass
from fractions import Fraction
from typing import Dict, List, Optional, Tuple
import re

__all__ = [
    "generate_reactions",
    "balance_equation",
    "parse_formula",
    "generate_balanced_equations",
    "format_balanced_equation",
    "parse_reactants_from_string",
    "ionic_and_net_equation",
    "try_all_reaction_paths",
    "pretty_format_variant",
    "enable_ascii_steps",
]

# Timeout utilities
import multiprocessing
import traceback


def _run_with_timeout(func, args=(), kwargs=None, timeout: float = 5.0):
    """Run func(*args, **kwargs) in a separate process with timeout (seconds).

    Returns the function result or raises TimeoutError on timeout, or re-raises worker exception.
    """
    if kwargs is None:
        kwargs = {}

    def _worker(q, fn, args, kwargs):
        try:
            res = fn(*args, **kwargs)
            q.put((True, res))
        except Exception:
            tb = traceback.format_exc()
            q.put((False, tb))

    q = multiprocessing.Queue()
    p = multiprocessing.Process(target=_worker, args=(q, func, args, kwargs))
    p.start()
    p.join(timeout)
    if p.is_alive():
        try:
            p.terminate()
        except Exception:
            pass
        p.join()
        raise TimeoutError(f"Operation timed out after {timeout} seconds")
    if q.empty():
        raise RuntimeError("Worker finished but returned no result")
    ok, payload = q.get()
    if ok:
        return payload
    else:
        raise RuntimeError(f"Worker error:\n{payload}")


def generate_reactions_with_timeout(reactants: List[str], timeout: float = 5.0) -> List[Dict]:
    """Safe wrapper around `generate_reactions` with a timeout (seconds).

    Raises `TimeoutError` if computation exceeds `timeout` seconds.
    """
    return _run_with_timeout(generate_reactions, args=(reactants,), timeout=timeout)


def generate_balanced_equations_with_timeout(reactants: List[str], timeout: float = 5.0) -> List[Dict]:
    """Wrapper around `generate_balanced_equations` with a timeout."""
    return _run_with_timeout(generate_balanced_equations, args=(reactants,), timeout=timeout)


# export new helpers
__all__.extend([
    'generate_reactions_with_timeout',
    'generate_balanced_equations_with_timeout',
])


### Набор данных (упрощённый)
# Упрощённая таблица растворимости: True = растворимо, False = малорастворимо/осадок
SOLUBILITY = {
    # Common insoluble (typical precipitates)
    'AgCl': False, 'AgBr': False, 'AgI': False,
    'PbCl2': False, 'PbSO4': False, 'PbCO3': False,
    'BaSO4': False, 'CaCO3': False, 'CaSO4': False,
    'Fe(OH)3': False, 'Al(OH)3': False, 'Mg(OH)2': False, 'Ca(OH)2': False,
    # Common soluble salts
    'NaCl': True, 'KCl': True, 'LiCl': True,
    'NaNO3': True, 'KNO3': True, 'NH4NO3': True,
    'Na2SO4': True, 'K2SO4': True, 'Na2CO3': True, 'K2CO3': True,
    'NaOH': True, 'KOH': True, 'NH4Cl': True,
    'AgNO3': True, 'Na2S': True, 'K2S': True,
    'NaClO': True, 'KClO': True, 'NaClO3': True, 'KClO3': True,
    # common hydroxides and oxides (approx.)
    'FeO': False, 'Fe2O3': False,
}

# Ряд напряжений металлов (от более активных к менее)
METAL_ACTIVITY = [
    "Li", "K", "Ba", "Ca", "Na", "Mg", "Al", "Zn", "Fe", "Ni",
    "Sn", "Pb", "H", "Cu", "Ag", "Au", "Pt"
]

# Частые валентности (METAL_COMMON_CHARGES) и таблица катионов/анионов
# CATION_CHARGES хранит список возможных зарядов (от наиболее типичного к менее типичным).
# METAL_COMMON_CHARGES даёт одно типичное значение, используемое для быстрой генерации солей.

CATION_CHARGES = {
    # common simple cations
    'H': [1], 'Li': [1], 'Be': [2], 'B': [3], 'C': [4], 'N': [3], 'O': [2], 'F': [1],
    'Na': [1], 'Mg': [2], 'Al': [3], 'Si': [4], 'P': [5,3], 'S': [2,4,6], 'Cl': [1], 'Ar': [0],
    'K': [1], 'Ca': [2], 'Sc': [3], 'Ti': [4,3], 'V': [2,3,4,5], 'Cr': [2,3,6], 'Mn': [2,4,7],
    'Fe': [2,3], 'Co': [2,3], 'Ni': [2], 'Cu': [1,2], 'Zn': [2], 'Ga': [3], 'Ge': [2,4],
    'As': [3,5], 'Se': [2,4,6], 'Br': [1,5], 'Kr': [0], 'Rb': [1], 'Sr': [2], 'Y': [3],
    'Zr': [4], 'Nb': [3,5], 'Mo': [3,6], 'Tc': [6], 'Ru': [3,4,8], 'Rh': [3,4], 'Pd': [2,4],
    'Ag': [1], 'Cd': [2], 'In': [3], 'Sn': [2,4], 'Sb': [3,5], 'Te': [2,4,6], 'I': [1], 'Xe': [0],
    'Cs': [1], 'Ba': [2], 'La': [3], 'Ce': [3,4], 'Pr': [3], 'Nd': [3,4], 'Pm': [3], 'Sm': [3],
    'Eu': [3], 'Gd': [3], 'Tb': [3,4], 'Dy': [3], 'Ho': [3], 'Er': [3], 'Tm': [3], 'Yb': [3],
    'Lu': [3], 'Hf': [4], 'Ta': [5], 'W': [6], 'Re': [2,4,6,7], 'Os': [3,4,6,8], 'Ir': [3,4,6],
    'Pt': [2,4,6], 'Au': [1,2,3], 'Hg': [1,2], 'Tl': [1,3], 'Pb': [2,4], 'Bi': [3], 'Po': [2,4],
    'At': [1], 'Rn': [0], 'Fr': [1], 'Ra': [2], 'Ac': [3], 'Th': [4], 'Pa': [5], 'U': [3,4,6],
}

# For quick salt-building, pick one common metal charge (first in list where available)
METAL_COMMON_CHARGES = {}
for el, charges in CATION_CHARGES.items():
    if isinstance(charges, (list, tuple)) and charges:
        # prefer the smallest positive charge as common default
        pos = [c for c in charges if isinstance(c, int) and c > 0]
        METAL_COMMON_CHARGES[el] = pos[0] if pos else charges[0]
    elif isinstance(charges, int):
        METAL_COMMON_CHARGES[el] = charges

# Anion charges consolidated (from provided list)
ANION_CHARGES = {
    # Simple anions
    'H': 1, 'O': 2, 'F': 1, 'S': 2, 'Cl': 1, 'Br': 1, 'I': 1, 'N': 3,
    # Oxoanions
    'AsO4': 3, 'PO4': 3, 'AsO3': 3, 'HPO4': 2, 'H2PO4': 1,
    'SO4': 2, 'NO3': 1, 'HSO4': 1, 'NO2': 1, 'S2O3': 2, 'SO3': 2,
    'ClO4': 1, 'IO3': 1, 'ClO3': 1, 'BrO3': 1, 'ClO2': 1, 'ClO': 1, 'BrO': 1, 'IO': 1,
    'CO3': 2, 'CrO4': 2, 'HCO3': 1, 'Cr2O7': 2,
    # Organic anions
    'CH3COO': 1, 'C2H3O2': 1, 'HCOO': 1,
    # Other anions
    'CN': 1, 'NH2': 1, 'OCN': 1, 'O2': 2, 'SCN': 1, 'C2O4': 2, 'OH': 1, 'MnO4': 1,
    'ClO3': 1, 'ClO4': 1,
}

# Дополнения: расширим список анионов и таблицу растворимости
ANION_CHARGES.update({
    'S2O3': 2,   # thiosulfate
    'C2O4': 2,   # oxalate
    'ClO3': 1,   # chlorate
    'ClO2': 1,   # chlorite
    'H2PO4': 1,
    'PO3': 3,
    'BO3': 3,
    'NO': 1,
})
ANION_CHARGES.update({
    'ClO': 1,  # hypochlorite
    'BrO': 1,  # hypobromite
    'IO': 1,   # hypoiodite
    'ClO3': 1, # chlorate
})

SOLUBILITY.update({
    'K2CO3': True,
    'Na2CO3': True,
    'Ca(OH)2': False,
    'Mg(OH)2': False,
    'Al(OH)3': False,
    'NH4Cl': True,
    'Na2S': True,
    'AgCl': False,
    'AgBr': False,
    'AgI': False,
})

# Global option: use ASCII labels for steps/spectators (PowerShell UTF-8 issues)
USE_ASCII_STEPS = False
_SPECTATOR_LABEL_RU = 'спектатор'
_SPECTATOR_LABEL_EN = 'spectator'

def enable_ascii_steps(enable: bool = True):
    """Если True, заменяет метки шагов/спектаторов на ASCII-метки (англ.)."""
    global USE_ASCII_STEPS
    USE_ASCII_STEPS = bool(enable)

def _spectator_label() -> str:
    return _SPECTATOR_LABEL_EN if USE_ASCII_STEPS else _SPECTATOR_LABEL_RU


### Утилиты парсинга формул
token_re = re.compile(r"([A-Z][a-z]?|\(|\)|\d+)")


def is_ionic_candidate(formula: str) -> bool:
    """Эвристика: определяет, похоже ли соединение на ионное/солевое (а не органическое молекулу).

    Критерии (упрощённо):
    - содержит металлы из `METAL_ACTIVITY` в начале, или
    - содержит NH4 (аммоний), или
    - имеет скобки или цифры (индексы) и не похоже на органическое (C+H)
    """
    if not formula or not isinstance(formula, str):
        return False
    f = formula
    # явные ионные записи, например 'Fe3+'
    if re.match(r"^[A-Z][a-z]?\d*\+", f) or re.match(r"^[A-Z][a-z]?\d*-$", f):
        return True
    # ammonium
    if 'NH4' in f or f.startswith('NH4'):
        return True
    # metal at start
    m = re.match(r"^([A-Z][a-z]?)", f)
    if m and m.group(1) in METAL_ACTIVITY:
        return True
    # has parentheses or explicit indices -> likely inorganic
    if '(' in f or re.search(r"\d", f):
        # but if contains both C and H, consider organic and return False
        parsed = parse_formula(f)
        if parsed.get('C',0) and parsed.get('H',0):
            return False
        return True
    return False


def parse_formula(formula: str) -> Dict[str, int]:
    """Разбирает формулу и возвращает словарь {элемент: количество}.

    Поддерживает скобки и индексы: Al2(SO4)3 -> {Al:2, S:3, O:12}
    """
    tokens = token_re.findall(formula)

    def parse_tokens(idx: int = 0) -> Tuple[Dict[str, int], int]:
        counts: Dict[str, int] = {}
        i = idx
        while i < len(tokens):
            tok = tokens[i]
            if tok == '(':
                inner_counts, j = parse_tokens(i + 1)
                i = j
                mul = 1
                if i < len(tokens) and tokens[i].isdigit():
                    mul = int(tokens[i]); i += 1
                for k, v in inner_counts.items():
                    counts[k] = counts.get(k, 0) + v * mul
            elif tok == ')':
                return counts, i + 1
            elif tok.isdigit():
                # digit after element -> multiply last element
                # (handled in element branch)
                # If stray number appears, skip
                i += 1
            else:
                # element
                element = tok
                i += 1
                number = 1
                if i < len(tokens) and tokens[i].isdigit():
                    number = int(tokens[i]); i += 1
                counts[element] = counts.get(element, 0) + number
        return counts, i

    counts, _ = parse_tokens(0)
    return counts


def is_valid_formula(formula: str) -> bool:
    """Quick sanity check for formula-like strings to avoid pathological inputs.

    Accepts letters, digits, parentheses and trailing +/- charges. Rejects very long or empty strings.
    """
    if not formula or not isinstance(formula, str):
        return False
    if len(formula) > 80:
        return False
    # allowed characters: letters, digits, parentheses, plus, minus
    if not re.match(r"^[A-Za-z0-9()\+\-]+$", formula):
        return False
    # tokenise and ensure at least one element token
    toks = token_re.findall(formula)
    return len(toks) > 0


def _parse_charge_suffix(formula: str) -> Tuple[str, int]:
    """Возвращает (формула_без_заряда, суммарный_заряд).

    Поддерживает суффиксы типа '2+', '+', '3-' и т.п.
    Если заряд не указан, возвращает 0.
    """
    if not formula or not isinstance(formula, str):
        return formula, 0
    m = re.search(r"(\d*[+-])$", formula)
    if not m:
        return formula, 0
    s = m.group(1)
    base = formula[:m.start()]
    if s in ('+', '-'):
        val = 1 if s == '+' else -1
    else:
        num = int(s[:-1]) if s[:-1].isdigit() else 1
        val = num if s[-1] == '+' else -num
    return base, val


def compute_oxidation_states(formula: str) -> Dict[str, int]:
    """Попытка вычислить формальные степени окисления для всех элементов в формуле.

    Возвращает словарь {element: oxidation_state} с целыми значениями, где возможно.
    Это эвристическая реализация, достаточная для генерации кандидатов полуреакций.
    """
    base, net_charge = _parse_charge_suffix(formula)
    parsed = parse_formula(base)
    typical = {'H': 1, 'O': -2, 'F': -1, 'Cl': -1, 'Br': -1, 'I': -1}

    def assumed_oxi(el: str) -> Optional[int]:
        if el in typical:
            return typical[el]
        if el in METAL_COMMON_CHARGES:
            return METAL_COMMON_CHARGES[el]
        if el == 'S':
            return -2
        if el == 'N':
            return -3
        return None

    results: Dict[str, int] = {}
    elems = list(parsed.keys())
    for target in elems:
        ct_target = parsed.get(target, 1)
        sum_others = net_charge
        unknowns = []
        for el, cnt in parsed.items():
            if el == target:
                continue
            a = assumed_oxi(el)
            if a is None:
                unknowns.append((el, cnt))
            else:
                sum_others += a * cnt

        if not unknowns:
            ox = -sum_others / ct_target
            if float(ox).is_integer():
                results[target] = int(ox)
            else:
                results[target] = int(Fraction(ox).limit_denominator())
        else:
            contrib = 0
            unresolved = False
            for el_u, cnt_u in unknowns:
                a2 = assumed_oxi(el_u)
                if a2 is None:
                    unresolved = True
                    break
                contrib += a2 * cnt_u
            if not unresolved:
                sum_others += contrib
                ox = -sum_others / ct_target
                if float(ox).is_integer():
                    results[target] = int(ox)
                else:
                    results[target] = int(Fraction(ox).limit_denominator())
            else:
                results[target] = 0
    return results


def generate_half_reaction_candidates(reactants: List[str]) -> List[Tuple[List[str], List[str], str]]:
    """Генерирует кандидатов полуреакций: (lhs_list, rhs_list, description).

    Эвристические шаблоны покрывают распространённые случаи: перманганат, дихромат,
    перекись водорода, галогены, распространённые металлы.
    """
    candidates: List[Tuple[List[str], List[str], str]] = []
    medium = detect_medium(reactants)

    def add(lhs, rhs, desc):
        candidates.append((lhs if isinstance(lhs, list) else [lhs], rhs if isinstance(rhs, list) else [rhs], desc))

    for r in reactants:
        # permanganate
        if 'MnO4' in r:
            if medium == 'acidic':
                add(r, 'Mn2+', 'Permanganate reduced to Mn2+ (acidic)')
            else:
                add(r, 'MnO2', 'Permanganate reduced to MnO2 (neutral/basic)')

        # dichromate
        if 'Cr2O7' in r or 'Cr2O7' in r:
            if medium == 'acidic':
                add(r, 'Cr3+', 'Dichromate reduced to Cr3+ (acidic)')
            else:
                add(r, 'Cr2O3', 'Dichromate reduced to Cr2O3 (neutral/basic)')

        # peroxide
        if 'H2O2' in r:
            add('H2O2', 'O2', 'Peroxide -> O2 (oxidation half)')
            add('H2O2', 'H2O', 'Peroxide -> H2O (reduction half)')

        # halogens
        if re.fullmatch(r'(Cl|Br|I)2', r) or r in ('Cl2','Br2','I2'):
            hal = r[:-1] if r.endswith('2') else r
            add(r, hal + '-', f'{r} reduced to {hal}- (halide)')
            if medium in ('basic', 'neutral'):
                add(r, hal + 'O', f'{r} oxidized to hypohalite {hal}O (neutral/basic)')

        # metal atoms or metal salts
        m = metal_from_formula(r)
        if m:
            common = METAL_COMMON_CHARGES.get(m)
            # oxidation 2+ -> 3+
            if common == 2:
                add(r, f"{m}3+", f"{m}2+ -> {m}3+ (common oxidation)")
            # elemental metal -> cation
            if re.fullmatch(rf"{m}", r):
                ch = METAL_COMMON_CHARGES.get(m, 2)
                add(r, f"{m}{ch}+" if ch>1 else f"{m}+", f"Elemental {m} -> {m}{ch}+ (salt formation)")

    return candidates


### Балансировка уравнений (матрица элементов × соединения)
def balance_equation(reactants: List[str], products: List[str]) -> Optional[Tuple[List[int], List[int]]]:
    """Балансирует уравнение. Возвращает кортеж списков коэффициентов (reactants, products) или None.

    Метод: составляет однородную систему Ax = 0 и находит целочисленное решение.
    """
    # собираем элементы
    comps = reactants + products
    elem_set = set()
    parsed = [parse_formula(c) for c in comps]
    for p in parsed:
        elem_set.update(p.keys())
    elements = sorted(elem_set)

    # матрица: строки = элементы, колонки = соединения
    # реактанты положительные, продукты отрицательные
    M: List[List[Fraction]] = []
    for el in elements:
        row = []
        for i, p in enumerate(parsed):
            coeff = p.get(el, 0)
            if i < len(reactants):
                row.append(Fraction(coeff))
            else:
                row.append(Fraction(-coeff))
        M.append(row)

    # Найдём ненулевой вектор x (столбец) такой, что M x = 0
    # Простейший подход: приведение к ступенчатому виду и подбор свободной переменной = 1
    # Работает для небольшого числа соединений.
    rows = len(M)
    cols = len(M[0])
    # Представим матрицу как расширенную с дробями
    A = [list(r) for r in M]

    # Прямой Гаусс (row echelon)
    r = 0
    pivot_cols = []
    for c in range(cols):
        # найти строку с непустым элементом в столбце c
        pivot = None
        for i in range(r, rows):
            if A[i][c] != 0:
                pivot = i; break
        if pivot is None:
            continue
        A[r], A[pivot] = A[pivot], A[r]
        pivot_val = A[r][c]
        # нормализуем строку
        A[r] = [val / pivot_val for val in A[r]]
        for i in range(rows):
            if i != r and A[i][c] != 0:
                factor = A[i][c]
                A[i] = [A[i][j] - factor * A[r][j] for j in range(cols)]
        pivot_cols.append(c)
        r += 1
        if r == rows:
            break

    # Определим свободные переменные: те столбцы, которые не в pivot_cols
    free_cols = [c for c in range(cols) if c not in pivot_cols]
    if not free_cols:
        # Только нулевая свобода — нет ненулевого решения
        return None

    # Попробуем несколько вариантов выбора свободной переменной, чтобы получить положительные коэффициенты
    candidates = []
    # защита от зависания: ограничим число свободных столбцов, которые пробуем
    max_free_try = 6
    free_to_try = free_cols[:max_free_try]
    for free in free_to_try:
        for free_val in range(1, max_free_try + 1):
            sol_try = [Fraction(0) for _ in range(cols)]
            sol_try[free] = Fraction(free_val)
            row_idx = 0
            for c in pivot_cols:
                s = Fraction(0)
                for j in range(c + 1, cols):
                    s += A[row_idx][j] * sol_try[j]
                sol_try[c] = -s
                row_idx += 1

            # Преобразуем в целые
            denoms = [f.denominator for f in sol_try]
            from math import gcd
            from functools import reduce
            lcm = 1
            for d in denoms:
                lcm = lcm * d // gcd(lcm, d)
            ints_try = [int(f * lcm) for f in sol_try]
            if all(v == 0 for v in ints_try):
                continue
            nonzero = [abs(v) for v in ints_try if v != 0]
            if nonzero:
                g = reduce(gcd, nonzero)
                ints_try = [v // g for v in ints_try]

            react_coeffs_try = ints_try[: len(reactants)]
            prod_coeffs_try = ints_try[len(reactants) :]
            # prefer solutions where all coefficients are positive (no zeros)
            if all(c > 0 for c in react_coeffs_try) and all(c > 0 for c in prod_coeffs_try):
                candidates.append((sum(abs(v) for v in ints_try), ints_try))

    # Если нашли подходящие варианты, выберем с минимальной суммой коэффициентов
    if candidates:
        candidates.sort(key=lambda x: x[0])
        ints = candidates[0][1]
    else:
        # fallback — старое поведение (первый свободный столбец)
        sol = [Fraction(0) for _ in range(cols)]
        free = free_cols[0]
        sol[free] = Fraction(1)
        row_idx = 0
        for c in pivot_cols:
            s = Fraction(0)
            for j in range(c + 1, cols):
                s += A[row_idx][j] * sol[j]
            sol[c] = -s
            row_idx += 1
        denoms = [f.denominator for f in sol]
        from math import gcd
        from functools import reduce

        lcm = 1
        for d in denoms:
            lcm = lcm * d // gcd(lcm, d)
        ints = [int(f * lcm) for f in sol]
        nonzero = [abs(v) for v in ints if v != 0]
        if nonzero:
            g = reduce(gcd, nonzero)
            ints = [v // g for v in ints]

    # У нас есть окончательный массив ints (либо из candidates, либо из fallback)

    react_coeffs = ints[: len(reactants)]
    prod_coeffs = ints[len(reactants) :]
    # If some product/reactant coefficients are zero or non-positive, try a small brute-force search
    if any(c <= 0 for c in react_coeffs) or any(c <= 0 for c in prod_coeffs):
        # small brute-force only for small systems to avoid combinatorial explosion
        total_species = len(reactants) + len(products)
        if total_species > 6:
            return None
        from collections import Counter
        from itertools import product
        max_coeff = 5
        found = None
        for r_choice in product(range(1, max_coeff + 1), repeat=len(reactants)):
            left = Counter()
            for coef, comp in zip(r_choice, parsed[:len(reactants)]):
                for el, cnt in comp.items():
                    left[el] += coef * cnt
            for p_choice in product(range(1, max_coeff + 1), repeat=len(products)):
                right = Counter()
                for coef, comp in zip(p_choice, parsed[len(reactants):]):
                    for el, cnt in comp.items():
                        right[el] += coef * cnt
                if left == right:
                    found = (list(r_choice), list(p_choice))
                    break
            if found:
                break
        if found:
            react_coeffs, prod_coeffs = found
        else:
            # No valid all-positive integer solution found in the small search — treat as unbalanced
            return None
    # Проверка: никакая сторона не должна быть весь нулевой
    if all(c == 0 for c in react_coeffs) or all(c == 0 for c in prod_coeffs):
        return None
    return react_coeffs, prod_coeffs


def _charge_of_species(species: str) -> int:
    """Return an estimated integer charge for some common ionic species.

    This is a heuristic: returns +1 for 'H+', -1 for 'OH-' or 'e', and 0 for most neutral molecules.
    """
    if not species or not isinstance(species, str):
        return 0
    if species == 'H+':
        return 1
    if species == 'OH-' or species == 'OH':
        return -1 if species.endswith('-') else 0
    if species == 'e':
        return -1
    # simple detection for explicit +/- in formula (e.g., Cl- or Na+)
    # support trailing numeric charge like 'Mn2+' or 'SO4 2-'
    m = re.match(r"^(.+?)(\d+)?([+-])$", species)
    if m:
        mag = int(m.group(2)) if m.group(2) else 1
        sign = m.group(3)
        return mag if sign == '+' else -mag
    # fallback: try ANION_CHARGES for known anions (negative)
    key = species.strip('()')
    if key in ANION_CHARGES:
        return -ANION_CHARGES.get(key, 0)
    # known simple cations
    if species in METAL_COMMON_CHARGES:
        return METAL_COMMON_CHARGES.get(species, 0)
    return 0


def balance_with_aux(reactants: List[str], products: List[str], medium: str = 'neutral') -> Optional[Tuple[List[int], List[int]]]:
    """Balance equation allowing auxiliary species H2O, H+, OH- and electrons.

    medium: 'acidic'|'basic'|'neutral' influences which auxiliary species are allowed.
    Returns (react_coeffs, prod_coeffs) or None.
    """
    from fractions import Fraction
    # build set of elements
    comps = list(reactants) + list(products)
    # allowed auxiliaries (we include left and right copies so solver can place them on either side)
    base_aux = []
    if medium == 'acidic':
        base_aux = ['H2O', 'H+']
    elif medium == 'basic':
        base_aux = ['H2O', 'OH-']
    else:
        # neutral: allow both H2O and OH- to give flexibility for neutral/basic balances
        base_aux = ['H2O', 'OH-']
    # create left and right copies of auxiliaries and electrons so they may appear on either side
    aux_left = list(base_aux)
    aux_right = list(base_aux)
    # electrons as a special auxiliary (allow on either side)
    aux_left.append('e')
    aux_right.append('e')

    all_species = comps + aux_left + aux_right
    def _parse_special(s: str):
        # parse species possibly with trailing numeric charge, e.g. Mn2+
        if s == 'e':
            return {}
        # remove trailing charge for composition parsing
        m = re.match(r"^(.+?)(\d+)?([+-])$", s)
        if m:
            base = m.group(1)
            return parse_formula(base)
        if s == 'H+':
            return {'H': 1}
        if s == 'OH-' or s == 'OH':
            return {'O': 1, 'H': 1}
        return parse_formula(s)

    parsed = [_parse_special(s) for s in all_species]

    # elements rows (exclude 'e')
    elem_set = set()
    for p in parsed:
        elem_set.update(p.keys())
    elements = sorted(elem_set)
    # build matrix rows: elements + charge
    rows = []
    for el in elements:
        row = []
        for i, p in enumerate(parsed):
            cnt = p.get(el, 0)
            # reactants positive, products negative, aux considered positive side (we'll treat signs later by index)
            row.append(Fraction(cnt))
        rows.append(row)
    # charge row
    charge_row = []
    for s in all_species:
        charge_row.append(Fraction(_charge_of_species(s)))
    rows.append(charge_row)

    # Now we need to set sign convention: reactants columns positive, products negative, aux columns depend (we'll keep as variables and treat equality)
    cols = len(all_species)
    A = [list(r) for r in rows]

    # We want sum(reactant_counts * coeffs_reactants) == sum(product_counts * coeffs_products) + sum(aux_counts * coeffs_aux)
    # This can be rearranged to A_full * x = 0 where columns for reactants are positive, products negative, aux positive on products side -> we move to left
    # To construct homogeneous system, we set sign = +1 for reactants, -1 for products, and -1 for aux (since aux placed on product side)
    signs = []
    n_react = len(reactants)
    n_prod = len(products)
    n_aux = len(aux_left)
    # order: [reactants..., products..., aux_left..., aux_right...]
    for i in range(len(all_species)):
        if i < n_react:
            signs.append(Fraction(1))
        elif i < n_react + n_prod:
            signs.append(Fraction(-1))
        elif i < n_react + n_prod + n_aux:
            # aux_left: treat as additional reactant-side auxiliaries
            signs.append(Fraction(1))
        else:
            # aux_right: treat as additional product-side auxiliaries
            signs.append(Fraction(-1))

    # Multiply each column by sign to get homogeneous eqn
    for i in range(len(A)):
        for j in range(cols):
            A[i][j] *= signs[j]

    # Solve A x = 0 similar to balance_equation
    rows_n = len(A)
    cols_n = cols
    # gaussian elimination
    M = [list(r) for r in A]
    r = 0
    pivot_cols = []
    for c in range(cols_n):
        pivot = None
        for i in range(r, rows_n):
            if M[i][c] != 0:
                pivot = i; break
        if pivot is None:
            continue
        M[r], M[pivot] = M[pivot], M[r]
        pv = M[r][c]
        M[r] = [val / pv for val in M[r]]
        for i in range(rows_n):
            if i != r and M[i][c] != 0:
                factor = M[i][c]
                M[i] = [M[i][j] - factor * M[r][j] for j in range(cols_n)]
        pivot_cols.append(c)
        r += 1
        if r == rows_n:
            break

    free_cols = [c for c in range(cols_n) if c not in pivot_cols]
    if not free_cols:
        return None

    # try assigning small integers to free cols
    from math import gcd
    from functools import reduce
    candidates = []
    # avoid exploring too many free variables for large systems
    max_free_try_aux = 6
    free_to_try_aux = free_cols[:max_free_try_aux]
    for free in free_to_try_aux:
        for v in range(1, max_free_try_aux + 1):
            sol = [Fraction(0) for _ in range(cols_n)]
            sol[free] = Fraction(v)
            row_idx = 0
            for c in pivot_cols:
                s = Fraction(0)
                for j in range(c + 1, cols_n):
                    s += M[row_idx][j] * sol[j]
                sol[c] = -s
                row_idx += 1
            denoms = [s.denominator for s in sol]
            lcm = 1
            for d in denoms:
                lcm = lcm * d // gcd(lcm, d)
            ints = [int(s * lcm) for s in sol]
            if all(vv == 0 for vv in ints):
                continue
            nonzero = [abs(vv) for vv in ints if vv != 0]
            g = reduce(gcd, nonzero) if nonzero else 1
            ints = [vv // g for vv in ints]
            # interpret coefficients: split into reactants/products/aux
            r_coeffs = ints[:n_react]
            p_coeffs = ints[n_react:n_react + n_prod]
            aux_coeffs = ints[n_react + n_prod:]
            # require reactant and product coefficients >0
            if all(c > 0 for c in r_coeffs) and all(c > 0 for c in p_coeffs):
                # ensure auxiliary coefficients are integers (can be zero)
                candidates.append((sum(abs(x) for x in ints), ints))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    best = candidates[0][1]
    react_coeffs = best[:n_react]
    prod_coeffs = best[n_react:n_react + n_prod]
    # If solution found, return
    return react_coeffs, prod_coeffs


def half_reaction_balance(reactants: List[str], products: List[str], medium: str = 'neutral') -> Optional[Dict]:
    """Balance a half-reaction, returning coefficients including electrons if present.

    Returns dict: {'reactants': [...], 'products': [...], 'react_coeffs': [...], 'prod_coeffs': [...], 'electrons': n}
    or None if cannot balance.
    """
    # Preprocess salts: for common salts like KMnO4 convert to anion MnO4 if possible
    def _salt_to_anion(s: str) -> str:
        # match leading cation (e.g., K, K2, Na, etc.)
        m = re.match(r"^([A-Z][a-z]?\d*)(.+)$", s)
        if m:
            head = m.group(1)
            tail = m.group(2)
            # strip leading digits in tail
            tail = tail
            key = tail.strip('()')
            if key in ANION_CHARGES:
                return key
        return s

    r_proc = [_salt_to_anion(s) for s in reactants]
    p_proc = [_salt_to_anion(s) for s in products]

    # Try aux-aware balance where we allow electrons explicitly on either side
    b = try_balance(r_proc, p_proc, medium)
    if not b:
        return None
    r_coeffs, p_coeffs = b
    # No explicit electrons returned by try_balance (they were internal aux) — we attempt to detect net electron change
    # We'll attempt another call forcing 'e' into products and reactants to find electron coefficient
    # Append e to products and try to balance (operate on processed lists)
    b2 = try_balance(r_proc, p_proc + ['e'], medium)
    if b2:
        rc2, pc2 = b2
        # electron coefficient is last of pc2
        electrons = pc2[-1]
        return {
            'reactants': reactants,
            'products': products,
            'react_coeffs': rc2,
            'prod_coeffs': pc2[:-1],
            'electrons': electrons,
        }
    # try electrons on reactant side
    b3 = try_balance(r_proc + ['e'], p_proc, medium)
    if b3:
        rc3, pc3 = b3
        electrons = rc3[-1]
        return {
            'reactants': reactants,
            'products': products,
            'react_coeffs': rc3[:-1],
            'prod_coeffs': pc3,
            'electrons': -electrons,  # negative means electrons produced on product side
        }
    # fallback: no explicit electron found — return coefficients without electrons
    return {
        'reactants': reactants,
        'products': products,
        'react_coeffs': r_coeffs,
        'prod_coeffs': p_coeffs,
        'electrons': 0,
    }


def combine_half_reactions(h1: Dict, h2: Dict) -> Optional[Tuple[List[int], List[int], List[str]]]:
    """Combine two half-reactions (h1 oxid, h2 red or vice versa) into full balanced equation.

    h1/h2 are dicts returned by half_reaction_balance. Returns (react_coeffs, prod_coeffs, species_list)
    where species_list is [reactants..., products...].
    """
    # Determine electrons produced/consumed
    e1 = h1.get('electrons', 0)
    e2 = h2.get('electrons', 0)
    # electrons sign convention: positive means on product side (produced), negative means consumed
    # We want to multiply halves so that electron counts cancel: n1*e1 + n2*e2 == 0
    if e1 == 0 and e2 == 0:
        # simple concatenation if no electrons involved
        reactants = h1['reactants'] + h2['reactants']
        products = h1['products'] + h2['products']
        # combine coeffs
        rcoeffs = h1['react_coeffs'] + h2['react_coeffs']
        pcoeffs = h1['prod_coeffs'] + h2['prod_coeffs']
        return rcoeffs, pcoeffs, reactants + products
    # else find multipliers m1,m2 such that m1*e1 + m2*e2 == 0
    from math import gcd
    if e1 == 0 or e2 == 0:
        return None
    # find least common multiple
    def lcm(a, b):
        return abs(a * b) // gcd(a, b)
    L = lcm(abs(e1), abs(e2))
    m1 = L // abs(e1)
    m2 = L // abs(e2)
    # scale coefficients
    rcoeffs_full = [c * m1 for c in h1['react_coeffs']] + [c * m2 for c in h2['react_coeffs']]
    pcoeffs_full = [c * m1 for c in h1['prod_coeffs']] + [c * m2 for c in h2['prod_coeffs']]
    reactants = h1['reactants'] + h2['reactants']
    products = h1['products'] + h2['products']
    # cancel identical species between products and reactants
    # combine counts for each unique species
    from collections import Counter
    left = Counter()
    right = Counter()
    for coef, sp in zip(rcoeffs_full, reactants):
        left[sp] += coef
    for coef, sp in zip(pcoeffs_full, products):
        right[sp] += coef
    # subtract common
    for sp in list(left.keys()):
        if sp in right:
            common = min(left[sp], right[sp])
            left[sp] -= common
            right[sp] -= common
            if left[sp] == 0:
                del left[sp]
            if right[sp] == 0:
                del right[sp]
    final_reactants = list(left.keys())
    final_rcoeffs = [left[s] for s in final_reactants]
    final_products = list(right.keys())
    final_pcoeffs = [right[s] for s in final_products]
    if not final_reactants or not final_products:
        return None
    return final_rcoeffs, final_pcoeffs, final_reactants + final_products


def try_balance(reactants: List[str], products: List[str], medium: str = 'neutral') -> Optional[Tuple[List[int], List[int]]]:
    """Try balancing using auxiliary-aware solver first, then fallback to classic balance_equation."""
    try:
        b = balance_with_aux(reactants, products, medium)
        if b:
            return b
    except Exception:
        pass

    # Try half-reaction based generation for detected oxidizer/reducer pairs
    def generate_half_variants(reacts: List[str]) -> List[ReactionVariant]:
        out: List[ReactionVariant] = []
        # simple lists of recognizable oxidizers and reducers
        oxidizers = ['MnO4', 'Cr2O7', 'Cl2', 'Br2', 'I2', 'NO3', 'ClO3', 'ClO4']
        reducers = ['H2O2', 'I-', 'I', 'Fe2+', 'Fe', 'SO3', 'S2O3', 'H2S', 'HS-', 'S2-', 'C2O4', 'H2']

        medium = detect_medium(reacts)

        # helper to check presence (allow salts like KMnO4 -> MnO4)
        def contains_key(key: str) -> bool:
            for r in reacts:
                if key in r:
                    return True
            return False

        found_ox = [k for k in oxidizers if contains_key(k)]
        found_red = [k for k in reducers if contains_key(k)]

        # also detect metal-based reducers (e.g., Fe in FeSO4 -> Fe2+)
        for r in reacts:
            m = metal_from_formula(r)
            if m:
                # if metal commonly has a +2 state, consider it a reducer
                common = METAL_COMMON_CHARGES.get(m)
                if common == 2 and (f'{m}2+' not in found_red):
                    found_red.append(f'{m}2+')
                # also if the formula explicitly contains element symbol at start, treat as possible reducer
                if re.match(rf'^{m}', r) and (m not in found_red):
                    found_red.append(m)

        # If still none detected, try scanning for common element markers (I, S)
        if not found_red:
            for r in reacts:
                if re.search(r"I2|I-|\bI\b", r):
                    found_red.append('I-')
                if re.search(r"S2O3|SO3|H2S|HS-|S2-", r):
                    found_red.append('S2-')

        for ox in found_ox:
            for rd in found_red:
                # build candidate product templates depending on ox and medium
                # permanganate
                if 'MnO4' in ox:
                    if medium == 'acidic':
                        prod_ox = ['Mn2+']
                    else:
                        prod_ox = ['MnO2']
                elif 'Cr2O7' in ox:
                    if medium == 'acidic':
                        prod_ox = ['Cr3+']
                    else:
                        prod_ox = ['Cr2O3']
                elif ox in ('Cl2','Br2','I2'):
                    # handled earlier; skip here
                    continue
                else:
                    # generic oxidizer: attempt to reduce oxygen-containing oxidizers to O2
                    prod_ox = ['O2']

                # reducer product templates
                if rd == 'H2O2':
                    prod_rd = ['O2']
                elif rd in ('I-','I'):
                    prod_rd = ['I2']
                elif rd.startswith('Fe'):
                    prod_rd = ['Fe3+']
                else:
                    prod_rd = []

                if not prod_rd:
                    continue

                # balance half-reactions
                h_ox = half_reaction_balance([ox], prod_ox, medium)
                h_rd = half_reaction_balance([rd], prod_rd, medium)
                if not h_ox or not h_rd:
                    continue
                comb = combine_half_reactions(h_ox, h_rd)
                if comb:
                    rcoeffs, pcoeffs, species_list = comb
                    try:
                        combined_products = list(species_list[len(rcoeffs):]) if len(species_list) > len(rcoeffs) else []
                        b = try_balance(reacts, combined_products, medium)
                        if b:
                            out.append(ReactionVariant('oxidation_reduction', reacts, combined_products, b, f'Half-reaction combination: {ox} + {rd}'))
                    except Exception:
                        pass
        # additionally, try heuristic-generated half-reaction candidates for broader coverage
        try:
            hr_cands = generate_half_reaction_candidates(reacts)
            # pairwise combine distinct candidates
            for i in range(len(hr_cands)):
                for j in range(i + 1, len(hr_cands)):
                    lhs1, rhs1, d1 = hr_cands[i]
                    lhs2, rhs2, d2 = hr_cands[j]
                    h1 = half_reaction_balance(lhs1, rhs1, medium)
                    h2 = half_reaction_balance(lhs2, rhs2, medium)
                    if not h1 or not h2:
                        continue
                    comb2 = combine_half_reactions(h1, h2)
                    if comb2:
                        rcoeffs, pcoeffs, species_list = comb2
                        try:
                            combined_products = list(species_list[len(rcoeffs):]) if len(species_list) > len(rcoeffs) else []
                            b2 = try_balance(reacts, combined_products, medium)
                            if b2:
                                out.append(ReactionVariant('oxidation_reduction', reacts, combined_products, b2, f'Heuristic half combo: {d1} + {d2}'))
                        except Exception:
                            pass
        except Exception:
            pass

        return out

    # Avoid expensive half-reaction generation for large numbers of reactants
    half_vars = []
    if len(reactants) <= 4:
        try:
            half_vars = generate_half_variants(reactants)
            # if any half-variant produced a direct balanced result, return it
            for hv in half_vars:
                if hv and hv.balanced:
                    return hv.balanced
        except Exception:
            half_vars = []
    # fallback
    try:
        return balance_equation(reactants, products)
    except Exception:
        return None


### Генерация вариантов реакций
@dataclass
class ReactionVariant:
    type: str
    reactants: List[str]
    products: List[str]
    balanced: Optional[Tuple[List[int], List[int]]]
    steps: str


def is_acid(formula: str) -> bool:
    # простая эвристика: начинается с H и не является H2O
    if not formula or not isinstance(formula, str):
        return False
    # Exclude peroxides like H2O2 which start with H but are not typical acids
    if formula.startswith("H2O2") or (formula.startswith('H') and 'O2' in formula):
        return False
    return formula.startswith("H") and formula != "H2O"


def is_base(formula: str) -> bool:
    # простая эвристика: содержит OH или имеет металлический катион и OH
    return "OH" in formula or formula.endswith("OH")


def detect_medium(reacts: List[str]) -> str:
    """Detect reaction medium: 'acidic', 'basic' or 'neutral'."""
    if any(is_base(r) for r in reacts) or any('OH' in r for r in reacts):
        return 'basic'
    if any(is_acid(r) for r in reacts):
        return 'acidic'
    return 'neutral'


def metal_from_formula(formula: str) -> Optional[str]:
    # Попытка получить металлический символ в начале формулы
    m = re.match(r"^([A-Z][a-z]?)", formula)
    if m:
        el = m.group(1)
        if el in METAL_ACTIVITY:
            return el
    return None


def decomposition_variant(reactants: List[str]) -> Optional[ReactionVariant]:
    # handle common decomposition patterns
    if len(reactants) != 1:
        return None
    R = reactants[0]
    # CaCO3 -> CaO + CO2
    if R == 'CaCO3':
        products = ['CaO', 'CO2']
        steps = f"Термическое разложение: {R} -> CaO + CO2"
        balanced = balance_equation([R], products)
        return ReactionVariant('decomposition', [R], products, balanced, steps)
    # H2O2 -> H2O + O2
    if R == 'H2O2':
        products = ['H2O', 'O2']
        steps = f"Каталитическое разложение: 2 H2O2 -> 2 H2O + O2"
        balanced = balance_equation([R], products)
        return ReactionVariant('decomposition', [R], products, balanced, steps)
    # AgCl -> Ag + Cl2 (photochemical)
    if R == 'AgCl':
        products = ['Ag', 'Cl2']
        steps = f"Фотохимическое разложение: 2 AgCl -> 2 Ag + Cl2"
        balanced = balance_equation([R], products)
        return ReactionVariant('decomposition', [R], products, balanced, steps)
    # Electrolytic water splitting (as decomposition) when explicitly requested
    if R == 'H2O':
        products = ['H2', 'O2']
        steps = f"Электролитическое разложение (при электролизе): 2 H2O -> 2 H2 + O2"
        balanced = balance_equation([R], products)
        return ReactionVariant('decomposition', [R], products, balanced, steps)
    return None


def complex_formation_variant(reactants: List[str]) -> Optional[ReactionVariant]:
    # simple detection: Cu2+ + NH3 -> [Cu(NH3)x]2+
    # support: reactants may include ion-like strings 'Cu2+' or molecular 'CuSO4' + NH3
    # If explicit ion provided
    for r in reactants:
        if re.match(r"^[A-Z][a-z]?\d*\+", r):
            # find ammonia count (look for separate NH3 molecules or numeric coefficient)
            nh3_count = sum(1 for x in reactants if x == 'NH3')
            if nh3_count > 0:
                cation = re.match(r"^([A-Z][a-z]?)(\d*)\+", r).group(1)
                charge_m = re.match(r"^[A-Z][a-z]?(\d*)\+", r).group(1)
                charge = int(charge_m) if charge_m else 1
                product = f"[{cation}(NH3){nh3_count}]" + (f"{charge}+" if charge != 1 else "")
                steps = f"Комплексообразование: {' + '.join(reactants)} -> {product}"
                balanced = balance_equation(reactants, [product])
                return ReactionVariant('complex_formation', reactants, [product], balanced, steps)
    # fallback: if metal salt and excess NH3 -> complex
    if any(r == 'NH3' for r in reactants):
        for r in reactants:
            if r.endswith('SO4') or r.endswith('Cl') or r.endswith('NO3'):
                m = re.match(r"^([A-Z][a-z]?)", r)
                if m:
                    metal = m.group(1)
                    nh3_count = sum(1 for x in reactants if x == 'NH3')
                    product = f"[{metal}(NH3){nh3_count}]"
                    steps = f"Комплексообразование (эвристика): {' + '.join(reactants)} -> {product}"
                    balanced = balance_equation(reactants, [product])
                    return ReactionVariant('complex_formation', reactants, [product], balanced, steps)
    return None


def neutralization_variant(reactants: List[str]) -> Optional[ReactionVariant]:
    # Проверяем пары кислота + основание
    for a in reactants:
        for b in reactants:
            if a == b:
                continue
            if is_acid(a) and is_base(b):
                # Улучшённая генерация соли с учётом числа H в кислоте и числа OH в основании.
                parsed_acid = parse_formula(a)
                parsed_base = parse_formula(b)
                acid_H = parsed_acid.get('H', 0)

                # определяем число OH групп в основании
                def base_oh_count(formula: str) -> int:
                    # ищем (OH)n
                    m = re.search(r"\(OH\)(\d*)", formula)
                    if m:
                        return int(m.group(1)) if m.group(1) else 1
                    m = re.search(r"OH(\d*)", formula)
                    if m:
                        return int(m.group(1)) if m.group(1) else 1
                    if formula.endswith('OH'):
                        return 1
                    return 0

                base_OH = base_oh_count(b)

                # если не удалось определить группы OH, пробуем старый способ (строковая эвристика)
                if base_OH == 0:
                    # fallback
                    try:
                        if '(OH)' in b:
                            base_cat = re.match(r"^([A-Z][a-z]?)", b).group(1)
                        elif b.endswith('OH'):
                            base_cat = b[:-2]
                        else:
                            base_cat = metal_from_formula(b) or b
                    except Exception:
                        base_cat = metal_from_formula(b) or b
                    acid_root_m = re.match(r"^H\d*(.*)$", a)
                    acid_root = acid_root_m.group(1) if acid_root_m else a[1:]
                    salt = base_cat + acid_root
                    salt = _normalize_formula(salt)
                    products = [salt, 'H2O']
                    steps = f"Нейтрализация (эвристика): {a} + {b} -> {salt} + H2O"
                    balanced = balance_equation([a, b], products)
                    return ReactionVariant('neutralization', [a, b], products, balanced, steps)

                # определяем катион (символ металла)
                cation = metal_from_formula(b) or re.match(r"^([A-Z][a-z]?)", b).group(1)
                # получаем корень кислоты (удаляем ведущие H и цифры)
                m = re.match(r"^H(\d*)(.*)$", a)
                acid_root = m.group(2) if m else a[1:]

                from math import gcd
                g = gcd(acid_H, base_OH)
                cation_sub = acid_H // g
                anion_sub = base_OH // g

                # формируем формулу соли: cation (с индексом если >1) + acid_root (с индексом если >1)
                cat_part = f"{cation}{cation_sub if cation_sub>1 else ''}"
                # если анион полиятомный (содержит более одного элемента), берем форму (anion)N
                elems = re.findall(r"[A-Z][a-z]?", acid_root)
                if anion_sub > 1 and len(elems) > 1:
                    an_part = f"({acid_root}){anion_sub}"
                else:
                    an_part = f"{acid_root}{anion_sub if anion_sub>1 else ''}"
                salt = (cat_part + an_part)
                salt = _normalize_formula(salt)

                products = [salt, 'H2O']
                steps = f"Нейтрализация: {a} + {b} -> {salt} + H2O"
                balanced = balance_equation([a, b], products)
                return ReactionVariant('neutralization', [a, b], products, balanced, steps)
    return None


def double_displacement_variant(reactants: List[str]) -> Optional[ReactionVariant]:
    # AB + CD -> AD + CB
    if len(reactants) != 2:
        return None
    A, B = reactants
    # Если это сочетание кислота + основание — это нейтрализация, не двойной обмен
    if (is_acid(A) and is_base(B)) or (is_acid(B) and is_base(A)):
        return None
    # Ограничение: применимо к ионным/солевым соединениям — оба реагента должны быть сложными (содержать >=2 элементов)
    try:
        parsed_a = parse_formula(A)
        parsed_b = parse_formula(B)
    except Exception:
        parsed_a = {}
        parsed_b = {}
    if not (len(parsed_a) >= 2 and len(parsed_b) >= 2):
        return None

    # Попробуем разбить на ионы по первой букве (упрощённо): катион = первая часть до первой заглавной нижней
    # На практике используем разделение на двух частей приблизительно
    def split_salt(s: str) -> Tuple[str, str]:
        # Попытка выделить катион и анион: если начинается с металла из METAL_ACTIVITY,
        # то катион — первые символы, остальное — анион. Иначе разбиваем по первому элементу.
        m = re.match(r"^([A-Z][a-z]?)(.*)$", s)
        if not m:
            return s, ""
        first, rest = m.group(1), m.group(2)
        if first in METAL_ACTIVITY:
            return first, rest or ""
        # иначе попробуем взять первый элемент как катион (эвристика)
        parts = re.findall(r"[A-Z][a-z]?\d*", s)
        if len(parts) >= 2:
            part1 = parts[0]
            rest = s[len(part1):]
            return part1, rest
        return s, ""

    a_cat, a_an = split_salt(A)
    b_cat, b_an = split_salt(B)

    def is_soluble(formula: str) -> bool:
        # enhanced fallback rules: nitrates, alkali metals and ammonium salts, acetates soluble
        if formula in SOLUBILITY:
            return SOLUBILITY.get(formula)
        # nitrates
        if 'NO3' in formula or 'NO2' in formula:
            return True
        # acetates
        if 'C2H3O2' in formula or 'CH3COO' in formula:
            return True
        # alkali metals and ammonium
        if formula.startswith(('Na','K','Li','Cs','Rb','NH4')):
            return True
        return True

    # Попытка учесть заряды анионов для корректного формирования формул продуктов
    def build_salt(cation: str, cation_charge: int, anion: str, anion_charge: int) -> str:
        from math import gcd
        g = gcd(cation_charge, anion_charge)
        cat_sub = anion_charge // g
        an_sub = cation_charge // g
        # cation part
        cat_part = f"{cation}{cat_sub if cat_sub>1 else ''}"
        # anion part: если полиятомный, оборачиваем в скобки при индексе>1
        elems = re.findall(r"[A-Z][a-z]?", anion)
        if an_sub > 1 and len(elems) > 1:
            an_part = f"({anion}){an_sub}"
        else:
            an_part = f"{anion}{an_sub if an_sub>1 else ''}"
        return _normalize_formula(cat_part + an_part)

    # Если известны заряды анионов, используем их
    a_an_key = a_an if a_an in ANION_CHARGES else a_an.strip('()')
    b_an_key = b_an if b_an in ANION_CHARGES else b_an.strip('()')
    products = None
    if a_an_key in ANION_CHARGES or b_an_key in ANION_CHARGES:
        # определим заряды (если неизвестен, считаем 1)
        a_an_charge = ANION_CHARGES.get(a_an_key, 1)
        b_an_charge = ANION_CHARGES.get(b_an_key, 1)
        # cation charges соответствуют заряду анйона в исходной соли
        cation_a_charge = a_an_charge
        cation_b_charge = b_an_charge

        P = build_salt(a_cat, cation_a_charge, b_an.strip('()'), b_an_charge)
        Q = build_salt(b_cat, cation_b_charge, a_an.strip('()'), a_an_charge)
        products = [P, Q]
    else:
        # fallback: простая конкатенация (как раньше)
        P = _normalize_formula(a_cat + b_an)
        Q = _normalize_formula(b_cat + a_an)
        products = [P, Q]

    steps = f"Двойной обмен: {A} + {B} -> {products[0]} + {products[1]} (упрощённая генерация)"
    balanced = balance_equation([A, B], products)

    p_sol = is_soluble(P)
    q_sol = is_soluble(Q)
    if not p_sol or not q_sol:
        precip_note = "Образуется осадок" if (not p_sol or not q_sol) else ""
    else:
        precip_note = "Оба продукта растворимы (ионный обмен, осадок не образуется)"

    steps = f"Двойной обмен: {A} + {B} -> {P} + {Q} ({precip_note})"
    balanced = balance_equation([A, B], products)
    return ReactionVariant("double_displacement", [A, B], products, balanced, steps)


def combination_variant(reactants: List[str]) -> Optional[ReactionVariant]:
    # Simple combination/synthesis rules
    if len(reactants) < 2:
        return None
    # Examples: metal + halogen -> metal halide
    # H2 + O2 -> H2O (handled by combustion_variant), but try metal + halogen
    A, B = reactants[0], reactants[1]
    # metal element + diatomic halogen
    if re.fullmatch(r"[A-Z][a-z]?", A) and re.fullmatch(r"(Cl|Br|I)2", B):
        hal = B[:-1]
        product = f"{A}{hal}"
        steps = f"Соединение: {A} + {B} -> {product}"
        balanced = balance_equation([A, B], [product])
        return ReactionVariant('combination', reactants, [product], balanced, steps)
    # special case: hydrogen + oxygen -> water (combination)
    if (A == 'H2' and B == 'O2') or (A == 'O2' and B == 'H2'):
        products = ['H2O']
        steps = f"Простое соединение: 2 H2 + O2 -> 2 H2O"
        balanced = balance_equation([A, B], products)
        return ReactionVariant('combination', reactants, products, balanced, steps)
    # metal oxide + CO2 -> metal carbonate e.g., CaO + CO2 -> CaCO3
    if len(reactants) == 2 and re.match(r"^[A-Z][a-z]?[A-Za-z0-9()]*O\d*$", A) and B == 'CO2':
        # take metal symbol
        m = re.match(r"^([A-Z][a-z]?)", A)
        if m:
            metal = m.group(1)
            product = f"{metal}CO3"
            steps = f"Кислотно-основное соединение/карбонат: {A} + {B} -> {product}"
            balanced = balance_equation([A, B], [product])
            return ReactionVariant('combination', reactants, [product], balanced, steps)
    return None


def oxidation_reduction_variant(reactants: List[str]) -> Optional[ReactionVariant]:
    """Простейшая обработка диспропорционирования галогенов в щёлочи.

    Пример: Cl2 + 2 NaOH -> NaCl + NaClO + H2O
    """
    if len(reactants) < 2:
        return None

    # Handle diatomic halogen + water (neutral disproportionation)
    # Cl2 + H2O -> HCl + HClO
    if any(r == 'H2O' for r in reactants):
        for hal in ('Cl','Br','I'):
            if any(r == f"{hal}2" for r in reactants):
                other = [r for r in reactants if r != 'H2O' and r != f"{hal}2"]
                # allow just Cl2 + H2O or with other inert species ignored
                products = [f"H{hal}", f"H{hal}O"]
                steps = f"Redox disproportionation with water: {hal}2 + H2O -> H{hal} + H{hal}O"
                balanced = balance_equation(reactants, products)
                if balanced is not None:
                    return ReactionVariant('oxidation_reduction', reactants, products, balanced, steps)

    # try to detect a diatomic halogen among any reactants (Cl2, Br2, I2)
    hal_match = None
    for hal in ('Cl','Br','I'):
        for r in reactants:
            if r == f"{hal}2":
                # pick another reagent as "other" (first different one)
                others = [x for x in reactants if x != r]
                other = others[0] if others else None
                hal_match = (hal, r, other)
                break
        if hal_match:
            break

    cat = None
    if hal_match:
        hal, hal_formula, other = hal_match
        # require a base/alkali for halogen disproportionation
        if not other or not is_base(other):
            hal_match = None
        else:
            cat = metal_from_formula(other) or None
            if cat is None:
                if other.startswith('NH4'):
                    cat = 'NH4'
                else:
                    hal_match = None

    # We'll produce two plausible variants for halogen disproportionation if detected
    # 1) cold/dilute -> hypohalite (ClO-): Cl2 + 2 NaOH -> NaCl + NaClO + H2O
    # 2) hot/concentrated -> chlorate (ClO3-): 3 Cl2 + 6 NaOH -> 5 NaCl + NaClO3 + 3 H2O

    variants: List[ReactionVariant] = []
    if hal_match:
        halide = f"{cat}{hal}"
        hypohalite = f"{cat}{hal}O"
        products1 = [halide, hypohalite, 'H2O']
        steps1 = f"Redox disproportionation (cold/dilute): {hal_formula} + {other} -> {halide} + {hypohalite} + H2O"
        balanced1 = try_balance(reactants, products1, detect_medium(reactants))

        # chlorate variant
        chlorate = f"{cat}{hal}O3"
        products2 = [halide, chlorate, 'H2O']
        steps2 = f"Redox disproportionation (hot/concentrated): {hal_formula} + {other} -> {halide} + {chlorate} + H2O"
        balanced2 = try_balance(reactants, products2, detect_medium(reactants))

        if balanced1 is not None:
            variants.append(ReactionVariant('oxidation_reduction', reactants, products1, balanced1, steps1))
        if balanced2 is not None:
            variants.append(ReactionVariant('oxidation_reduction', reactants, products2, balanced2, steps2))

    # Also attempt more general redox handling for common oxidizers/reducers
    # (permanganate/dichromate with peroxide, etc.)
    try:
        # detect medium using module helper
        medium = detect_medium(reactants)

        # General: permanganate + peroxide
        if any("MnO4" in r for r in reactants) and any("H2O2" in r for r in reactants):
            mn = next(r for r in reactants if "MnO4" in r)
            per = 'H2O2'
            cat = metal_from_formula(mn) or (re.match(r"^([A-Z][a-z]?)", mn).group(1) if re.match(r"^([A-Z][a-z]?)", mn) else 'K')
            acidic_present = medium == 'acidic'
            # acidic variant: Mn2+ (as salt with available acid anion if present) + O2 + H2O
            acid_anion = None
            for r in reactants:
                if is_acid(r):
                    m = re.match(r"^H(\d*)(.*)$", r)
                    acid_anion = m.group(2) if m else None
            if acidic_present and acid_anion:
                # form Mn salt with that anion (e.g., MnSO4) and include spectator cation salt (e.g., K2SO4)
                mn_salt = f"Mn{acid_anion}"
                cat_salt = f"{cat}{acid_anion}"
                products_acid = ['O2', mn_salt, cat_salt, 'H2O']
                steps_acid = f"Redox (acidic): {mn} + {per} -> O2 + {mn_salt} + {cat_salt} + H2O"
                b_acid = try_balance(reactants, products_acid, 'acidic')
                if b_acid is not None:
                    variants.append(ReactionVariant('oxidation_reduction', reactants, products_acid, b_acid, steps_acid))
            # neutral/basic variant: MnO2 (s), O2, metal hydroxide, water
            hydroxide = f"{cat}OH"
            products_neutral = ['O2', 'MnO2', hydroxide, 'H2O']
            steps_neutral = f"Redox (neutral/basic): {mn} + {per} -> O2 + MnO2 + {hydroxide} + H2O"
            b_neu = try_balance(reactants, products_neutral, medium)
            if b_neu is not None:
                variants.append(ReactionVariant('oxidation_reduction', reactants, products_neutral, b_neu, steps_neutral))

        # Dichromate + peroxide (similar pattern)
        if any("Cr2O7" in r for r in reactants) and any("H2O2" in r for r in reactants):
            cr = next(r for r in reactants if "Cr2O7" in r)
            per = 'H2O2'
            cat = metal_from_formula(cr) or (re.match(r"^([A-Z][a-z]?)", cr).group(1) if re.match(r"^([A-Z][a-z]?)", cr) else 'K')
            # acidic: Cr3+ salt if acid anion present
            acid_anion = None
            for r in reactants:
                if is_acid(r):
                    m = re.match(r"^H(\d*)(.*)$", r)
                    acid_anion = m.group(2) if m else None
            if acid_anion:
                cr_salt = f"Cr{acid_anion}"
                cat_salt = f"{cat}{acid_anion}"
                products_acid = ['O2', cr_salt, cat_salt, 'H2O']
                steps_acid = f"Redox (acidic): {cr} + {per} -> O2 + {cr_salt} + {cat_salt} + H2O"
                b_acid = try_balance(reactants, products_acid, 'acidic')
                if b_acid is not None:
                    variants.append(ReactionVariant('oxidation_reduction', reactants, products_acid, b_acid, steps_acid))
            # neutral/basic: Cr2O3 + O2 + metal hydroxide + H2O (approx)
            hydroxide = f"{cat}OH"
            products_neu = ['O2', 'Cr2O3', hydroxide, 'H2O']
            steps_neu = f"Redox (neutral/basic): {cr} + {per} -> O2 + Cr2O3 + {hydroxide} + H2O"
            b_neu = try_balance(reactants, products_neu, medium)
            if b_neu is not None:
                variants.append(ReactionVariant('oxidation_reduction', reactants, products_neu, b_neu, steps_neu))
    except Exception:
        pass

    # Return list of variants (generate_reactions will handle list return)
    return variants


def single_replacement_variant(reactants: List[str]) -> Optional[ReactionVariant]:
    A, BC = reactants
    # разрешаем замену только если A — простая формула/молекула (например 'Zn', 'Fe', 'Cl2', 'CH4')
    if not re.fullmatch(r"[A-Z][A-Za-z0-9()]*", A):
        return None
    A_m = metal_from_formula(A)
    # allow metals, diatomic halogens (Cl2) or hydrocarbons (CH4) as A
    if not (A_m is not None or re.fullmatch(r"(Cl|Br|I)2", A) or ("C" in A and "H" in A)):
        return None
    # попытка найти металлический элемент в BC
    m = re.match(r"^([A-Z][a-z]?)", BC)
    if not m:
        return None
    B = m.group(1)

    # Если A — металл
    if A_m is not None:
        if B not in METAL_ACTIVITY:
            # если вторым нет металла, возможно H (кислота)
            if BC.startswith("H"):
                # A + acid -> salt + H2 if A более активен H
                if METAL_ACTIVITY.index(A_m) < METAL_ACTIVITY.index("H"):
                    anion = BC[1:]
                    # попробуем подобрать формулу соли: вариации anion_n (n=3..1)
                    # сначала попытаемся сформировать соль используя известную валентность металла
                    anion_key = anion.strip('()')
                    anion_charge = ANION_CHARGES.get(anion_key, 1)
                    cat_charge = METAL_COMMON_CHARGES.get(A_m)
                    if cat_charge:
                        from math import gcd
                        g = gcd(cat_charge, anion_charge)
                        cat_sub = anion_charge // g
                        an_sub = cat_charge // g
                        cat_part = f"{A}{cat_sub if cat_sub>1 else ''}"
                        elems = re.findall(r"[A-Z][a-z]", anion)
                        if an_sub > 1 and len(elems) > 1:
                            an_part = f"({anion}){an_sub}"
                        else:
                            an_part = f"{anion}{an_sub if an_sub>1 else ''}"
                        cand = _normalize_formula(cat_part + an_part)
                        products = [cand, "H2"]
                        balanced = balance_equation([A, BC], products)
                        if balanced is not None:
                            steps = f"Замещение водорода: {A} + {BC} -> {cand} + H2"
                            return ReactionVariant("single_replacement", [A, BC], products, balanced, steps)
                    # fallback: пробуем несколько вариантов с индексами (3..1)
                    for an_sub in range(3, 0, -1):
                        # формируем candidate salt
                        elems = re.findall(r"[A-Z][a-z]", anion)
                        if an_sub > 1 and len(elems) > 1:
                            an_part = f"({anion}){an_sub}"
                        else:
                            an_part = f"{anion}{an_sub if an_sub>1 else ''}"
                        cand = _normalize_formula(f"{A}{an_part}")
                        products = [cand, "H2"]
                        balanced = balance_equation([A, BC], products)
                        if balanced is not None:
                            steps = f"Замещение водорода: {A} + {BC} -> {cand} + H2"
                            return ReactionVariant("single_replacement", [A, BC], products, balanced, steps)
                    # fallback: простая конкатенация
                    salt = _normalize_formula(f"{A}{anion}")
                    products = [salt, "H2"]
                    steps = f"Замещение водорода (эвристика): {A} + {BC} -> {salt} + H2"
                    balanced = balance_equation([A, BC], products)
                    return ReactionVariant("single_replacement", [A, BC], products, balanced, steps)
            return None
        # сравним активность
        if METAL_ACTIVITY.index(A_m) <= METAL_ACTIVITY.index(B):
            # A более активен (меньший индекс) или равен
            # AC + B
            # упрощённое формирование продукта: заменим катион B в BC на A
            rest = BC[len(B):]
            AC = A + rest
            products = [AC, B]
            steps = f"Одноэлементное замещение: {A} + {BC} -> {AC} + {B} (по ряду активности)"
            balanced = balance_equation([A, BC], products)
            return ReactionVariant("single_replacement", [A, BC], products, balanced, steps)

    # Если A — диатомный галоген (неметаллическое замещение)
    if re.fullmatch(r"(Cl|Br|I)2", A):
        # NaBr + Cl2 -> NaCl + Br2 (пример)
        # попробуем найти галогенид-анион в BC
        for hal in ('Cl','Br','I'):
            if BC.endswith(hal):
                # cation part
                m2 = re.match(r"^([A-Z][a-z]?\d*)", BC)
                if m2:
                    cat = m2.group(1)
                    new_salt = _normalize_formula(cat + A[:-1])
                    other_hal = hal
                    products = [new_salt, other_hal + '2']
                    steps = f"Неметаллическое замещение: {A} + {BC} -> {new_salt} + {other_hal}2"
                    balanced = balance_equation([A, BC], products)
                    return ReactionVariant("single_replacement", [A, BC], products, balanced, steps)

    # Органическое радикальное замещение (элементарный случай для CH4 и др.)
    if re.fullmatch(r"[A-Z][a-z]?\d*", A) and A.endswith('2') and 'C' in BC and 'H' in BC:
        # e.g., CH4 + Cl2 -> CH3Cl + HCl
        parsed = parse_formula(BC)
        if parsed.get('C',0) == 1 and parsed.get('H',0) >= 1 and A in ('Cl2','Br2'):
            # form monosubstituted
            new_parsed = parsed.copy()
            new_parsed['H'] = new_parsed.get('H',0) - 1
            new_parsed['Cl' if A.startswith('Cl') else 'Br'] = 1
            # build formula string
            def dict_to_formula(d):
                s = ''
                for el, cnt in d.items():
                    s += f"{el}{cnt if cnt>1 else ''}"
                return s
            product1 = dict_to_formula(new_parsed)
            product2 = 'HCl' if A.startswith('Cl') else 'HBr'
            products = [product1, product2]
            steps = f"Радикальное замещение (упрощенно): {BC} + {A} -> {product1} + {product2}"
            balanced = balance_equation([BC, A], products)
            return ReactionVariant('single_replacement', [A, BC], products, balanced, steps)
    # Also handle swapped order: hydrocarbon + diatomic halogen
    if re.fullmatch(r"[A-Z][a-z]?\d*", BC) and BC.endswith('2') and 'C' in A and 'H' in A:
        parsed = parse_formula(A)
        if parsed.get('C',0) == 1 and parsed.get('H',0) >= 1 and BC in ('Cl2','Br2'):
            new_parsed = parsed.copy()
            new_parsed['H'] = new_parsed.get('H',0) - 1
            new_parsed['Cl' if BC.startswith('Cl') else 'Br'] = 1
            def dict_to_formula(d):
                s = ''
                for el, cnt in d.items():
                    s += f"{el}{cnt if cnt>1 else ''}"
                return s
            product1 = dict_to_formula(new_parsed)
            product2 = 'HCl' if BC.startswith('Cl') else 'HBr'
            products = [product1, product2]
            steps = f"Радикальное замещение (упрощенно): {A} + {BC} -> {product1} + {product2}"
            balanced = balance_equation([A, BC], products)
            return ReactionVariant('single_replacement', [A, BC], products, balanced, steps)
    return None


def combustion_variant(reactants: List[str]) -> Optional[ReactionVariant]:
    # простая проверка углеводорода + O2 -> CO2 + H2O
    if len(reactants) != 2:
        return None
    a, b = reactants
    # обнаружим O2
    if a == "O2":
        hydro = b
    elif b == "O2":
        hydro = a
    else:
        return None
    parsed = parse_formula(hydro)
    if "C" in parsed and "H" in parsed:
        c = parsed.get("C", 0)
        h = parsed.get("H", 0)
        products = ["CO2", "H2O"]
        steps = f"Горение: {hydro} + O2 -> CO2 + H2O"
        balanced = balance_equation([hydro, "O2"], products)
        return ReactionVariant("combustion", [hydro, "O2"], products, balanced, steps)
    return None


def generate_reactions(reactants: List[str]) -> List[Dict]:
    """Генерирует возможные варианты реакций для списка реагентов.

    Возвращает список словарей с подробностями.
    """
    # quick validation: reject pathological inputs to avoid hangs
    if not isinstance(reactants, list) or any(not is_valid_formula(r) for r in reactants):
        return []
    # limit extreme input sizes for safety
    if len(reactants) > 8:
        return []

    variants: List[ReactionVariant] = []
    # Попробуем нейтрализацию
    n = neutralization_variant(reactants)
    if n:
        variants.append(n)
    # Комбинация / синтез
    cmb = combination_variant(reactants)
    if cmb:
        variants.append(cmb)
    # Окислительно-восстановительные диспропорционирования (галогены в щёлочи и т.п.)
    red = oxidation_reduction_variant(reactants)
    red_found = False
    if red:
        # oxidation_reduction_variant may return a single ReactionVariant or a list
        if isinstance(red, list):
            variants.extend(red)
            red_found = len(red) > 0
        else:
            variants.append(red)
            red_found = True
    # специальный случай: разложение угольной кислоты H2CO3 -> CO2 + H2O
    if any(r == 'H2CO3' for r in reactants):
        # разложение без основания
        steps = "Разложение H2CO3: H2CO3 -> CO2 + H2O"
        b = balance_equation(['H2CO3'], ['CO2', 'H2O'])
        variants.append(ReactionVariant('carbonic_decomposition', ['H2CO3'], ['CO2', 'H2O'], b, steps))
    # Двойной обмен (для двух соединений) — пропускаем, если уже найден редокс
    if not red_found:
        d = double_displacement_variant(reactants)
        if d:
            variants.append(d)
    # Разложение (термическое/каталитическое и т.д.)
    dec = decomposition_variant(reactants)
    if dec:
        variants.append(dec)
    # Комплексообразование
    comp = complex_formation_variant(reactants)
    if comp:
        variants.append(comp)
    # Замещение — применимо только для двух реагентов; пропускаем, если уже найден редокс
    if not red_found and len(reactants) == 2:
        s = single_replacement_variant(reactants)
        if s:
            variants.append(s)
    # Горение
    c = combustion_variant(reactants)
    if c:
        variants.append(c)

    # Преобразуем в словари
    out = []
    for v in variants:
        # Basic validation: require a balanced integer solution with all-positive coefficients
        b = v.balanced
        if b is None:
            # skip unbalanced/undetermined variants here (they may be noisy)
            continue
        r_coeffs, p_coeffs = b
        if any(c <= 0 for c in r_coeffs) or any(c <= 0 for c in p_coeffs):
            continue
        # validate product formulas look plausible
        valid_prods = True
        for p in v.products:
            if not _is_valid_formula(p):
                valid_prods = False; break
            try:
                parsed_p = parse_formula(p)
                if not parsed_p:
                    valid_prods = False; break
            except Exception:
                valid_prods = False; break
        if not valid_prods:
            continue
        out.append({
            "type": v.type,
            "reactants": v.reactants,
            "products": v.products,
            "balanced": (v.balanced if v.balanced else None),
            "steps": v.steps,
        })
    return out


### Форматирование результатов
def _normalize_formula(s: str) -> str:
    # Нормализация частых представлений
    if s == "HOH":
        return "H2O"
    return s


def format_balanced_equation(reactants: List[str], products: List[str], balanced: Optional[Tuple[List[int], List[int]]]) -> Optional[str]:
    """Возвращает строку полностью сбалансированного уравнения, например "2 H2 + O2 -> 2 H2O".
    Если balanced is None, возвращает None.
    """
    if balanced is None:
        return None
    r_coeffs, p_coeffs = balanced

    def fmt_side(comps: List[str], coeffs: List[int]) -> str:
        parts = []
        for comp, c in zip(comps, coeffs):
            comp_n = _normalize_formula(comp)
            if c == 0:
                continue
            if c == 1:
                parts.append(comp_n)
            else:
                parts.append(f"{c} {comp_n}")
        return " + ".join(parts) if parts else ""

    left = fmt_side(reactants, r_coeffs)
    right = fmt_side(products, p_coeffs)
    if not left or not right:
        return None
    return f"{left} -> {right}"





def _is_valid_formula(s: str) -> bool:
    if not s or not isinstance(s, str):
        return False
    return bool(re.search(r"[A-Za-z]", s))


def pretty_format_variant(v: Dict) -> str:
    """Вернёт удобочитаемую строку с подробностями варианта реакции."""
    lines: List[str] = []
    lines.append(f"Type: {v.get('type')}")
    eq = v.get('equation') or format_balanced_equation(v.get('reactants', []), v.get('products', []), v.get('balanced'))
    if eq:
        lines.append(f"Equation: {eq}")
    prods = v.get('products')
    if prods:
        lines.append(f"Products: {', '.join(prods)}")
    if v.get('balanced'):
        lines.append(f"Balanced coeffs: {v.get('balanced')}")
    if v.get('full_ionic'):
        lines.append(f"Full ionic: {v.get('full_ionic')}")
    if v.get('intermediate'):
        lines.append(f"Intermediate: {v.get('intermediate')}")
    if v.get('net_ionic'):
        lines.append(f"Net ionic: {v.get('net_ionic')}")
    if v.get('steps'):
        lines.append(f"Steps: {v.get('steps')}")
    if v.get('reason'):
        lines.append(f"Reason: {v.get('reason')}")
    return "\n".join(lines)


def generate_balanced_equations(reactants: List[str]) -> List[Dict]:
    """Возвращает варианты реакций с уже форматированными сбалансированными уравнениями.

    Формат элемента списка:
    {"type": str, "equation": Optional[str], "reactants": [...], "products": [...], "balanced": ... , "steps": str}
    """
    raw = generate_reactions(reactants)
    out = []
    for v in raw:
        # нормализуем формулы продуктов
        prods = [ _normalize_formula(p) for p in v["products"] ]
        eq = format_balanced_equation(v["reactants"], prods, v["balanced"]) if v.get("balanced") else None
        # Если balanced отсутствует, но реакция потенциально ионная (обмен/нейтрализация/разложение),
        # попытаться сформировать ионное/промежуточное представление используя коэффициенты 1.
        if v.get("balanced") is None and v.get("type") in ("double_displacement", "neutralization", "single_replacement", "carbonic_decomposition"):
            trial_bal = ([1] * len(v["reactants"]), [1] * len(prods))
            ionic = ionic_and_net_equation(v["reactants"], prods, trial_bal)
            # пометим шаги, что ионное представление может быть несбалансировано
            if ionic and ionic.get("intermediate"):
                v["steps"] = (v.get("steps", "") + "\n(Ионное представление показано с коэффициентами 1, может быть несбалансировано)")
        else:
            ionic = ionic_and_net_equation(v["reactants"], prods, v.get("balanced"))
        out.append({
            "type": v["type"],
            "equation": eq,
            "reactants": v["reactants"],
            "products": prods,
            "balanced": v.get("balanced"),
            "steps": v["steps"],
            "full_ionic": ionic.get("full_ionic") if ionic else None,
            "intermediate": ionic.get("intermediate") if ionic else None,
            "net_ionic": ionic.get("net_ionic") if ionic else None,
        })
    return out


### Ионные уравнения и промежуточные представления
def _base_oh_count(formula: str) -> int:
    m = re.search(r"\(OH\)(\d*)", formula)
    if m:
        return int(m.group(1)) if m.group(1) else 1
    m = re.search(r"OH(\d*)", formula)
    if m:
        return int(m.group(1)) if m.group(1) else 1
    if formula.endswith('OH'):
        return 1
    return 0


def _decompose_to_ions(formula: str, coef: int = 1) -> List[Tuple[str, int, str]]:
    """Возвращает список (ion_str, count, kind) для данного соединения с учётом коэффициента.
    kind: 'ion' или 'molecule'
    """
    formula = _normalize_formula(formula)
    parsed = parse_formula(formula)
    ions: List[Tuple[str, int, str]] = []

    # вода и другие молекулы остаются молекулами
    if formula in ("H2O", "CO2"):
        ions.append((formula, coef, 'molecule'))
        return ions

    # основания: M(OH)n -> M^{n}+ + n OH-
    oh_count = _base_oh_count(formula)
    if oh_count > 0:
        # cation is metal at start
        cat = metal_from_formula(formula) or re.match(r"^([A-Z][a-z]?)", formula).group(1)
        # cation charge equals number of OH groups (e.g., Ca(OH)2 -> Ca2+)
        c_charge = oh_count
        cat_ion = f"{cat}{'' if c_charge==1 else str(c_charge)}+"
        ions.append((cat_ion, coef * 1, 'ion'))
        ions.append((f"OH-", coef * oh_count, 'ion'))
        return ions

    # кислоты: HnX -> n H+ + X^{charge-}
    if is_acid(formula):
        h_count = parsed.get('H', 0)
        anion = formula
        # remove leading H digits
        m = re.match(r"^H(\d*)(.*)$", formula)
        anion = m.group(2) if m else formula[1:]
        anion_key = anion.strip('()')
        anion_charge = ANION_CHARGES.get(anion_key, 1)
        # H+ ions
        if h_count > 0:
            ions.append(("H+", coef * h_count, 'ion'))
        ions.append((f"{anion}{'' if anion_charge==1 else str(anion_charge)+'-'}", coef * 1, 'ion'))
        return ions

    # соли: пытаемся найти известный анион только если формула похоже на ионную (не органическую)
    if is_ionic_candidate(formula):
        for anion_key in sorted(ANION_CHARGES.keys(), key=lambda x: -len(x)):
            # искать вхождение аниона и возможный индекс после него
            m = re.search(rf"{re.escape(anion_key)}(\d*)", formula)
            if not m:
                continue
            idx = m.start()
            # если катионная часть отсутствует (например "Cl2"), это не соль
            cat_part = formula[:idx]
            if not cat_part:
                continue
            an_sub = int(m.group(1)) if m.group(1) else 1
            an_part = anion_key
            # разбор катионной части: получить символ и количество
            cat_parsed = parse_formula(cat_part) if cat_part else {}
            # выберем основной катион (первый элемент, или тот, что в CATION_CHARGES)
            cat_sym = None
            cat_count = 0
            for el, cnt in cat_parsed.items():
                if el in CATION_CHARGES:
                    cat_sym = el; cat_count = cnt; break
            if cat_sym is None and cat_parsed:
                # возьмём первый элемент
                for el, cnt in cat_parsed.items():
                    cat_sym = el; cat_count = cnt; break
            if not cat_sym:
                # как fallback: попробуем взять метальный символ в начале
                m2 = re.match(r"^([A-Z][a-z]?)", formula)
                cat_sym = m2.group(1) if m2 else formula
                cat_count = 1

            an_charge = ANION_CHARGES.get(anion_key, 1)

            # определяем заряд катиона
            if cat_sym in CATION_CHARGES:
                val = CATION_CHARGES[cat_sym]
                if isinstance(val, (list, tuple)) and val:
                    c_charge = val[0]
                else:
                    c_charge = val
            else:
                # попытаемся вывести из уравнения нейтральности: cat_count * c_charge = an_sub * an_charge
                from math import gcd
                try:
                    numerator = an_sub * an_charge
                    denom = cat_count if cat_count>0 else 1
                    # ищем минимальное целое c_charge, такое что (cat_count * c_charge) == numerator
                    if numerator % denom == 0:
                        c_charge = numerator // denom
                    else:
                        # приближённо — используем частное, округлённое вверх к целому делителю
                        # пытаемся найти множитель k от 1..4 чтобы сделать целым
                        found = False
                        for k in range(1, 5):
                            if (numerator * k) % denom == 0:
                                c_charge = (numerator * k) // denom
                                found = True
                                break
                        if not found:
                            c_charge = 1
                except Exception:
                    c_charge = 1

            # Формируем строковые обозначения и количество ионов
            cat_ion = f"{cat_sym}{'' if c_charge==1 else str(c_charge)}+"
            an_ion = f"{an_part}{'' if an_charge==1 else str(an_charge)}-"
            ions.append((cat_ion, coef * (cat_count if cat_count>0 else 1), 'ion'))
            ions.append((an_ion, coef * an_sub, 'ion'))
            return ions

    # fallback: treat as molecule
    ions.append((formula, coef, 'molecule'))
    return ions


def _balance_ionic_equation(reactants: List[str], products: List[str]) -> Optional[Tuple[List[int], List[int]]]:
    """Попытка сбалансировать уравнение на уровне ионов.
    Строим систему уравнений для каждого иона (кол-во ионов по соединениям) и ищем ненулевое целочисленное решение.
    """
    # собрать уникальные ионы (строки) и матрицу (rows = ions, cols = compounds)
    comps = reactants + products
    ion_list = []
    comp_ion_counts: List[Dict[str,int]] = []
    for comp in comps:
        parts = _decompose_to_ions(comp, 1)
        d: Dict[str,int] = {}
        for ion, cnt, kind in parts:
            if kind != 'ion':
                continue
            d[ion] = d.get(ion, 0) + cnt
            if ion not in ion_list:
                ion_list.append(ion)
        comp_ion_counts.append(d)

    if not ion_list:
        return None

    # Матрица: строки = ионы, столбцы = соединения
    from fractions import Fraction
    M: List[List[Fraction]] = []
    for ion in ion_list:
        row: List[Fraction] = []
        for i, d in enumerate(comp_ion_counts):
            cnt = d.get(ion, 0)
            # reactants positive, products negative
            if i < len(reactants):
                row.append(Fraction(cnt))
            else:
                row.append(Fraction(-cnt))
        M.append(row)

    # Решаем M x = 0 (повторяя алгоритм из balance_equation)
    rows = len(M)
    cols = len(M[0])
    A = [list(r) for r in M]
    r = 0
    pivot_cols = []
    for c in range(cols):
        pivot = None
        for i in range(r, rows):
            if A[i][c] != 0:
                pivot = i; break
        if pivot is None:
            continue
        A[r], A[pivot] = A[pivot], A[r]
        pv = A[r][c]
        A[r] = [val / pv for val in A[r]]
        for i in range(rows):
            if i != r and A[i][c] != 0:
                factor = A[i][c]
                A[i] = [A[i][j] - factor * A[r][j] for j in range(cols)]
        pivot_cols.append(c)
        r += 1
        if r == rows:
            break

    free_cols = [c for c in range(cols) if c not in pivot_cols]
    if not free_cols:
        return None

    sol = [Fraction(0) for _ in range(cols)]
    free = free_cols[0]
    sol[free] = Fraction(1)

    row_idx = 0
    for c in pivot_cols:
        s = Fraction(0)
        for j in range(c+1, cols):
            s += A[row_idx][j] * sol[j]
        sol[c] = -s
        row_idx += 1

    from math import gcd
    from functools import reduce
    denoms = [f.denominator for f in sol]
    lcm = 1
    for d in denoms:
        lcm = lcm * d // gcd(lcm, d)
    ints = [int(f * lcm) for f in sol]
    if all(v == 0 for v in ints):
        return None
    nonzero = [abs(v) for v in ints if v != 0]
    if nonzero:
        g = reduce(gcd, nonzero)
        ints = [v // g for v in ints]
    react_coeffs = ints[:len(reactants)]
    prod_coeffs = ints[len(reactants):]
    if all(c == 0 for c in react_coeffs) or all(c == 0 for c in prod_coeffs):
        return None
    return react_coeffs, prod_coeffs


def ionic_and_net_equation(reactants: List[str], products: List[str], balanced: Optional[Tuple[List[int], List[int]]]) -> Dict[str, Optional[str]]:
    """Возвращает словарь: full_ionic, intermediate, net_ionic (строки)"""
    used_unbalanced = False
    if balanced is None:
        # Попробуем сбалансировать уравнение на уровне ионов
        ionic_bal = _balance_ionic_equation(reactants, products)
        if ionic_bal is not None:
            balanced = ionic_bal
        else:
            # как запасной план — используем коэффициенты 1, но пометим, что это несбалансировано
            balanced = ([1] * len(reactants), [1] * len(products))
            used_unbalanced = True
    r_coeffs, p_coeffs = balanced
    left_ions: Dict[str, int] = {}
    right_ions: Dict[str, int] = {}
    left_mols: List[Tuple[str,int]] = []
    right_mols: List[Tuple[str,int]] = []

    # decompose
    for coef, comp in zip(r_coeffs, reactants):
        comps = _decompose_to_ions(comp, coef)
        for ion, count, kind in comps:
            if kind == 'ion':
                left_ions[ion] = left_ions.get(ion, 0) + count
            else:
                left_mols.append((ion, count))
    for coef, comp in zip(p_coeffs, products):
        comps = _decompose_to_ions(comp, coef)
        for ion, count, kind in comps:
            if kind == 'ion':
                right_ions[ion] = right_ions.get(ion, 0) + count
            else:
                right_mols.append((ion, count))

    # full ionic equation (ions on right/left) + molecules on respective sides
    def fmt_side_ions(ions_dict: Dict[str,int]) -> str:
        parts = []
        for ion, cnt in ions_dict.items():
            parts.append(f"{cnt} {ion}" if cnt!=1 else f"{ion}")
        return " + ".join(parts)

    left_str = fmt_side_ions(left_ions)
    right_str = fmt_side_ions(right_ions)
    # append molecules (they remain molecular)
    if left_mols:
        left_str = left_str + (" + " if left_str else "") + " + ".join(f"{c} {m}" if c!=1 else m for m,c in left_mols)
    if right_mols:
        right_str = right_str + (" + " if right_str else "") + " + ".join(f"{c} {m}" if c!=1 else m for m,c in right_mols)

    full_ionic = f"{left_str} -> {right_str}"

    # compute net ionic by cancelling common ions
    net_left = left_ions.copy()
    net_right = right_ions.copy()
    cancelled = {}
    for ion in list(net_left.keys()):
        if ion in net_right:
            cancel = min(net_left[ion], net_right[ion])
            net_left[ion] -= cancel
            net_right[ion] -= cancel
            cancelled[ion] = cancel
            if net_left[ion] == 0:
                del net_left[ion]
            if net_right.get(ion,0) == 0 and ion in net_right:
                del net_right[ion]

    # intermediate: show all ions but mark cancelled
    inter_left_parts = []
    for ion, cnt in left_ions.items():
        if ion in cancelled:
            inter_left_parts.append(f"[{cnt} {ion} ({_spectator_label()})]")
        else:
            inter_left_parts.append(f"{cnt} {ion}" if cnt!=1 else ion)
    inter_right_parts = []
    for ion, cnt in right_ions.items():
        if ion in cancelled:
            inter_right_parts.append(f"[{cnt} {ion} ({_spectator_label()})]")
        else:
            inter_right_parts.append(f"{cnt} {ion}" if cnt!=1 else ion)

    inter_left = " + ".join(inter_left_parts + [f"{c} {m}" if c!=1 else m for m,c in left_mols])
    inter_right = " + ".join(inter_right_parts + [f"{c} {m}" if c!=1 else m for m,c in right_mols])
    intermediate = f"{inter_left} -> {inter_right}"

    # net ionic formatting
    def fmt_net(ions_dict: Dict[str,int]) -> str:
        parts = []
        for ion, cnt in ions_dict.items():
            parts.append(f"{cnt} {ion}" if cnt!=1 else ion)
        return " + ".join(parts)

    net_left_str = fmt_net(net_left)
    net_right_str = fmt_net(net_right)
    # Добавим молекулярные продукты/реактанты в net-ионное уравнение
    if left_mols:
        mols = ' + '.join(f"{c} {m}" if c!=1 else m for m,c in left_mols)
        net_left_str = (net_left_str + ' + ' + mols) if net_left_str else mols
    if right_mols:
        mols = ' + '.join(f"{c} {m}" if c!=1 else m for m,c in right_mols)
        net_right_str = (net_right_str + ' + ' + mols) if net_right_str else mols

    net_ionic = (f"{net_left_str} -> {net_right_str}") if (net_left_str or net_right_str) else None

    return {"full_ionic": full_ionic, "intermediate": intermediate, "net_ionic": net_ionic}


### CLI-парсер простого вида "A + B" или "A,B"
def parse_reactants_from_string(s: str) -> List[str]:
    s = s.strip()
    # Поддерживаем синтаксис: "A + B" или "A,B" или "A B"
    parts = re.split(r"\s*\+\s*|\s*,\s*|\s+", s)
    parts = [p for p in parts if p]
    return parts


def try_all_reaction_paths(reactants: List[str]) -> Dict[str, List[Dict]]:
    """Пытается выполнить реакцию всеми доступными вариантами и возвращает два списка:
    - 'proceeded': варианты, которые реально идут (по эвристике: образуется вода/газ/осадок/элемент и т.п.)
    - 'possible_but_no_reaction': варианты, которые возможны по типу, но не идут из-за отсутствия движущей силы

    Каждый элемент списка — словарь с ключами: type, equation, products, balanced, steps, reason, full_ionic, intermediate, net_ionic
    """
    variants = generate_balanced_equations(reactants)
    proceeded = []
    blocked = []

    def is_insoluble(prod: str) -> bool:
        p = _normalize_formula(prod)
        if p in SOLUBILITY:
            return not SOLUBILITY[p]
        return False

    def has_gas_or_water(products: List[str]) -> bool:
        for p in products:
            if p in ('CO2', 'H2', 'O2'):
                return True
            if p == 'H2O':
                return True
        return False

    for v in variants:
        # Ensure reaction is balanced: if balanced is missing, try to compute it
        balanced = v.get('balanced')
        reactants_list = v.get('reactants') or reactants
        products_list = v.get('products') or []
        if balanced is None:
            try_bal = balance_equation(reactants_list, products_list)
            if try_bal is not None:
                v['balanced'] = try_bal
                balanced = try_bal
        # regenerate equation string if possible
        eq_str = v.get('equation')
        if not eq_str and v.get('balanced'):
            eq_str = format_balanced_equation(reactants_list, products_list, v.get('balanced'))

        rec = {k: v.get(k) for k in ('type', 'equation', 'products', 'balanced', 'steps')}
        # prefer updated equation
        rec['equation'] = eq_str
        # recompute ionic representations using balanced coefficients if available
        ionic = None
        if v.get('balanced'):
            ionic = ionic_and_net_equation(reactants_list, products_list, v.get('balanced'))
        else:
            ionic = ionic_and_net_equation(reactants_list, products_list, None)
        rec['full_ionic'] = ionic.get('full_ionic') if ionic else None
        rec['intermediate'] = ionic.get('intermediate') if ionic else None
        rec['net_ionic'] = ionic.get('net_ionic') if ionic else None

        t = v.get('type')
        prods = products_list
        reason = ''
        ok = False

        if t == 'neutralization':
            ok = True; reason = 'formation of water (neutralization)'
        elif t == 'double_displacement':
            if any(is_insoluble(p) for p in prods) or has_gas_or_water(prods):
                ok = True; reason = 'formation of insoluble product, gas or water'
            else:
                ok = False; reason = 'products appear soluble — likely no net reaction (no precipitate)'
        elif t == 'single_replacement':
            if any(re.fullmatch(r"[A-Z][a-z]?", p) for p in prods) or has_gas_or_water(prods) or any(is_insoluble(p) for p in prods):
                ok = True; reason = 'formation of element/gas/insoluble product'
            else:
                ok = False; reason = 'products soluble; replacement unlikely in solution'
        elif t in ('decomposition', 'combustion', 'combination', 'carbonic_decomposition', 'complex_formation', 'oxidation_reduction'):
            # accept if we were able to compute balancing
            if v.get('balanced'):
                ok = True; reason = 'balanced reaction (accepted)'
            else:
                ok = False; reason = 'unable to compute stoichiometry (unbalanced)'
        else:
            ok = bool(v.get('balanced')); reason = 'balanced (default)' if ok else 'no balanced stoichiometry'

        rec['reason'] = reason
        # add pretty formatted output for UI
        try:
            rec['pretty'] = pretty_format_variant(rec)
        except Exception:
            rec['pretty'] = ''
        if ok:
            proceeded.append(rec)
        else:
            blocked.append(rec)

    return {'proceeded': proceeded, 'possible_but_no_reaction': blocked}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        inp = " ".join(sys.argv[1:])
        reactants = parse_reactants_from_string(inp)
        print("Reactants:", reactants)
        res = generate_balanced_equations(reactants)
        if not res:
            print("No reaction variants generated")
        for v in res:
            print("Type:", v["type"]) 
            print("Equation:", v["equation"]) 
            print("Products:", v["products"]) 
            print("Balanced:", v["balanced"]) 
            print("Full ionic:", v.get("full_ionic"))
            print("Intermediate:", v.get("intermediate"))
            print("Net ionic:", v.get("net_ionic"))
            print("Steps:", v["steps"]) 
            print()
        examples = [
            ["HCl", "NaOH"],
            ["CuSO4", "NaOH"],
            ["Zn", "HCl"],
            ["CH4", "O2"],
        ]
        for ex in examples:
            print("---")
            print("Reactants:", ex)
            res = generate_balanced_equations(ex)
            if not res:
                print("No reaction variants generated")
            for r in res:
                print("Type:", r["type"]) 
                print("Equation:", r["equation"]) 
                print("Products:", r["products"]) 
                print("Balanced:", r["balanced"]) 
                print("Steps:", r["steps"])
            print()


if __name__ == "__main__":
    # Небольшая демонстрация
    examples = [
        ["HCl", "NaOH"],
        ["CuSO4", "NaOH"],
        ["Zn", "HCl"],
        ["Cl2", "O2"],
        ["KOH", "H2SO4"]
    ]
    for ex in examples:
        print("---")
        print("Reactants:", ex)
        res = generate_reactions(ex)
        if not res:
            print("No reaction variants generated")
        for r in res:
            print("Type:", r["type"]) 
            print("Products:", r["products"]) 
            print("Balanced:", r["balanced"]) 
            print("Steps:", r["steps"])
        print()
