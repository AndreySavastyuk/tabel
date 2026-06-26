# -*- coding: utf-8 -*-
"""Нормализация и нечёткое сопоставление ФИО.

`name_format` — дословный перенос SCUD.name_format (схлопывание пробелов);
идентичность сотрудника в старой системе строится только по нему.

Нечёткое сопоставление (`norm`/`tokens`/`lev`/`sim`/`fio_match`/`same_person`)
перенесено из назначить_отделы.py — используется веб-слоем для сверки сырых
ФИО из выгрузок с карточками сотрудников (экран reconciliation алиасов).
"""


def name_format(name):
    """'Иванов  Иван   Иванович' -> 'Иванов Иван Иванович'."""
    if name:
        name = name.split(" ")
        tmp = ""
        for i in name:
            if len(i) != 0:
                tmp = tmp + f'{i} '
        tmp = tmp[:-1]
        return tmp
    return name


# --- нечёткое сопоставление (из назначить_отделы.py) ---
def norm(s):
    return " ".join(str(s).lower().replace("ё", "е").split())


def tokens(s):
    return norm(s).split()


def lev(a, b):
    """Расстояние Левенштейна (для коротких строк)."""
    if a == b:
        return 0
    m, n = len(a), len(b)
    if abs(m - n) > 2:
        return 3
    prev = list(range(n + 1))
    for i in range(1, m + 1):
        cur = [i] + [0] * n
        for j in range(1, n + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[n]


def sim(a, b):
    """Похожи ли токены (имя/отчество): общий 4-символьный префикс или опечатка."""
    if not a or not b:
        return False
    if a[:4] == b[:4]:
        return True
    return lev(a, b) <= 1


def fio_match(entry, fio_toks):
    """Совпадает ли запись списка с ФИО. Фамилия — точно (после ё→е); имя/
    отчество — с допуском на опечатки."""
    e, f = entry, fio_toks
    if not e or not f or e[0] != f[0]:
        return False
    if len(e) >= 3:
        if len(f) >= 3:
            return sim(e[1], f[1]) and sim(e[2], f[2])
        return len(f) >= 2 and sim(e[1], f[1])
    if len(e) == 2:
        return len(f) >= 2 and sim(e[1], f[1])     # фамилия + имя
    return True                                     # только фамилия


def same_person(a_toks, b_toks):
    """Два ФИО — вероятно один человек (дубликат с опечаткой/ё/е)?"""
    if len(a_toks) >= 2 and len(b_toks) >= 2 and not sim(a_toks[1], b_toks[1]):
        return False
    if len(a_toks) >= 3 and len(b_toks) >= 3 and not sim(a_toks[2], b_toks[2]):
        return False
    return True
