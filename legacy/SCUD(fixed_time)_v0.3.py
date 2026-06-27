import pandas as pd
import json
import openpyxl
import os
import csv
from time import sleep as sleep
from datetime import datetime, date, time
from tkinter.filedialog import askopenfilename
import FileEditor as fe
import DateWorker as dw
import model
import refdata
import compute

# ============================================================================
# Фиксированное время прихода
# ----------------------------------------------------------------------------
# Для части сотрудников время прихода жёстко зафиксировано.
# Логика: если фактическое время прихода РАНЬШЕ фиксированного - в табель
# подставляется фиксированное время. Если ПОЗЖЕ или РАВНО - оставляется
# фактическое время прихода. Время ухода не меняется.
#
# Список сотрудников и их фикс. время хранится в общем файле:
#   <wp>/ЛЭЗ/Сотрудники.txt
# Формат строки: ФИО=ЧЧ:ММ   (например: Иванов Иван Иванович=07:40)
# Строки без "=" - обычные сотрудники без фиксации.
# Префиксы "!" / "!-" (удалённые) игнорируются при загрузке фикс. времени,
# но при перезаписи файла суффикс "=ЧЧ:ММ" сохраняется.
# ============================================================================
EMPLOYEES_FILENAME = "Сотрудники.txt"  #FIXID_TIME(v0.1)


def load_fixed_start_employees(wp):
    """Читает Сотрудники.txt и собирает {ФИО: "ЧЧ:ММ"} только по активным
    строкам, содержащим "=". Удалённые (помеченные "!"/"!-") пропускаются."""
    fixed = {}
    path = f'{wp}/ЛЭЗ/{EMPLOYEES_FILENAME}'
    try:
        with open(path, encoding="utf_8_sig") as fh:
            for line in fh.readlines():
                line = line.strip()
                if not line or line.startswith("!"):
                    continue
                if "=" not in line:
                    continue
                name_part, time_part = line.split("=", 1)
                name_part = name_part.strip()
                time_part = time_part.strip()
                if name_part and time_part:
                    fixed[name_format(name_part)] = time_part
    except Exception as e:
        print(f'load_fixed_start_employees: {e}')
        return fixed
    print(f'Сотрудников с фиксированным временем прихода: {len(fixed)}')
    return fixed


def _split_name_and_fixed(body):
    """Из 'ФИО=ЧЧ:ММ' возвращает (ФИО, 'ЧЧ:ММ' | None)."""
    if "=" in body:
        name_part, time_part = body.split("=", 1)
        name_part = name_part.strip()
        time_part = time_part.strip()
        return name_part, time_part if time_part else None
    return body.strip(), None


def read_employees_file(path, automatic):
    """Читает Сотрудники.txt с поддержкой суффикса '=ЧЧ:ММ'.
    Возвращает (emp, depl, fixed_times):
      emp/depl - списки чистых ФИО (без суффикса и без "!"/"!-");
      fixed_times - {ФИО (name_format): 'ЧЧ:ММ'} по всем строкам,
                    включая помеченные удалёнными - чтобы при перезаписи
                    не терять время для возможного возврата сотрудника."""
    emp = []
    depl = []
    fixed_times = {}
    try:
        with open(path, encoding="utf_8_sig") as fh:
            for raw in fh.readlines():
                line = raw.replace("\n", "")
                if not line.strip():
                    continue
                if "!" not in line:
                    body = line
                    target = emp
                elif "!-" in line:
                    body = line.replace("!-", "")
                    target = depl
                else:
                    if not automatic:
                        input(f'Требуется удалить {raw}')
                    body = line.replace("!", "")
                    target = depl
                name_clean, time_part = _split_name_and_fixed(body)
                if not name_clean:
                    continue
                if time_part:
                    fixed_times[name_format(name_clean)] = time_part
                target.append(name_clean)
    except Exception as e:
        print(str(e))
    return emp, depl, fixed_times


def write_employees_file(path, emp, depl, fixed_times):
    """Пишет Сотрудники.txt. Если для ФИО (нормализованного name_format)
    задан элемент в fixed_times - дописывает суффикс '=ЧЧ:ММ'."""
    with open(path, "w", encoding="utf_8_sig") as fh:
        for name in emp:
            t = fixed_times.get(name_format(name))
            fh.write(f'{name}={t}\n' if t else f'{name}\n')
        for name in depl:
            t = fixed_times.get(name_format(name))
            fh.write(f'!{name}={t}\n' if t else f'!{name}\n')


def apply_fixed_start_time(start_time, name, fixed_employees):
    """Если сотрудник в списке и пришёл раньше фикс. времени - подменяет start_time.

    start_time:      строка "DD.MM.YYYY HH:MM" либо False / " -"
    name:            ФИО, уже прошедшее name_format()
    fixed_employees: словарь {ФИО: "ЧЧ:ММ"}

    Возвращает кортеж (новый_start_time, был_ли_изменён)."""
    if not start_time or start_time is False or start_time == " -":
        return start_time, False
    if not fixed_employees or name not in fixed_employees:
        return start_time, False
    try:
        parts = start_time.split(" ")
        if len(parts) < 2:
            return start_time, False
        date_part, time_part = parts[0], parts[1]
        fix_hh, fix_mm = fixed_employees[name].split(":")
        fix_hh, fix_mm = int(fix_hh), int(fix_mm)
        act_hh, act_mm = time_part.split(":")[0], time_part.split(":")[1]
        act_hh, act_mm = int(act_hh), int(act_mm)
        # Строгое неравенство: при равенстве - оставляем фактическое (не помечаем).
        if (act_hh, act_mm) < (fix_hh, fix_mm):
            return f'{date_part} {fix_hh:02d}:{fix_mm:02d}', True
        return start_time, False
    except Exception as e:
        print(f'apply_fixed_start_time: ошибка для {name} ({start_time}): {e}')
        return start_time, False


def office(path):
    try:
        global f
        global base
        global points
        for row in path.data:
            if len(row) >= 9 and (row[5] !="" or row[7] != "" or row[4] != ""):
                #print(len(row), row)
                if row[4] != "Дата" and row[5] != "Время":
                    #print(row)
                    if base.get(name_format(row[0])) == None:
                        base[name_format(row[0])] = {}
                    if len(row) == 12:
                        if row[5] !="":
                            base[name_format(row[0])][date_format(f'{row[4]} {row[5]}')] = row[7]
                            d = date_format(f'{row[4]} {row[5]}')
                            n = name_format(row[0])
                            points[f'{n} {d}'] = "StorK"
                        if row[8] !="":
                            base[name_format(row[0])][date_format(f'{row[4]} {row[8]}')] = row[11]
                            d = date_format(f'{row[4]} {row[8]}')
                            n = name_format(row[0])
                            points[f'{n} {d}'] = "StorK"
                    elif len(row) == 10:
                        if row[4] != "":
                            base[name_format(row[0])][date_format(f'{row[3]} {row[4]}')] = row[6]
                            d = date_format(f'{row[3]} {row[4]}')
                            n = name_format(row[0])
                            points[f'{n} {d}'] = "StorK"
                        if row[7] != "":
                            base[name_format(row[0])][date_format(f'{row[3]} {row[7]}')] = row[9]
                            d = date_format(f'{row[3]} {row[7]}')
                            n = name_format(row[0])
                            points[f'{n} {d}'] = "StorK"
                    else:
                        # Неожиданная длина строки StorK — раньше тут был
                        # отладочный input() (подвешивал автозапуск). Просто
                        # предупреждаем и пропускаем строку.
                        print("office: неожиданная длина строки StorK", len(row), row)
            else:
                #print(row, len(row))
                pass
        #input(base)
        base = base_sort(base)
        #input(base)
        #print(base)
        #print(base)
    except Exception as e:
        print("office", str(e))

def ceh(path):
    try:
        global f
        global base
        global points
        #print(f.data[99][1])
        tmp = []
        A, C, E, G = None, None, None, None
        for row in path.data.get(99):
            if row.get("G") and row.get("G") !="направление":
                A = row.get("A", A)
                C = name_format(row.get("C", C))
                E = row.get("E", E)
                G = row.get("G", G)
                #print(A,C,E,G)
                if base.get(C) == None:
                    base[C] = {}
                base[C][date_format(f'{A} {E}')] = G
                d = date_format(f'{A} {E}')
                points[f'{C} {d}'] = "NC_SIGUR"
    except Exception as e:
        print("ceh", str(e))

def hikvision(path):
    try:
        global f
        global base
        global points
        # print(f.data[99][1])
        tmp = []
        for row in old_xls_reader(path):
            A = row.get("D").split(" ")[0]
            C = name_format(row.get("B"))
            E = row.get("D").split(" ")[1]
            G = row.get("E").replace("Приход", "Вход").replace("Уход", "Выход").replace("Нет", "Вход")
            # print(A,C,E,G)
            if base.get(C) == None:
                base[C] = {}
            base[C][date_format(f'{A} {E}')] = G
            d = date_format(f'{A} {E}')
            points[f'{C} {d}'] = row.get("F")
    except Exception as e:
        print("ceh", str(e))

def lez(path):
    try:
        global f
        global lezbase
        global points
        #print(f.data)
        #print(f.data[99][1])
        tmp = []
        A, C, E, G = None, None, None, None
        name = None
        for row in path.data.get(99):
            if row.get("G") == "Номер ключа:":
                name = name_format(row.get("A"))
            if row.get("I") == "Всего времени:":
                name = None
            if name and row.get("A") != "Устройство входа":
                if lezbase.get(name) == None:
                    lezbase[name] = {}
                if row.get("E") and row.get("F"):
                    lezbase[name][date_format(f'{row.get("E")} {row.get("F")}')] = "Вход"
                    d = date_format(f'{row.get("E")} {row.get("F")}')
                    n = name
                    points[f'{n} {d}'] = "LEZ"
                if row.get("J") and row.get("K"):
                    lezbase[name][date_format(f'{row.get("J")} {row.get("K")}')] = "Выход"
                    d = date_format(f'{row.get("J")} {row.get("K")}')
                    n = name
                    points[f'{n} {d}'] = "LEZ"
    except Exception as e:
        print("lez", str(e))

def base_sort(base):
    #print(base)
    new_base = {}
    for keys, dicts in base.items(): # ФИО: Словарнь событий
        tmpdict = {}
        k = list(dicts.keys()) # [ФИО]
        count = 0
        while count != len(k):
            k[count] = f'{k[count].split(".")[2].split(" ")[0]}.{k[count].split(".")[1]}.{k[count].split(".")[0]} {k[count].split(".")[2].split(" ")[1]}'
            count += 1
        k.sort()
        count = 0
        while count != len(k):
            k[count] = f'{k[count].split(".")[2].split(" ")[0]}.{k[count].split(".")[1]}.{k[count].split(".")[0]} {k[count].split(".")[2].split(" ")[1]}'
            count += 1
        for i in k:
            tmpdict[i] = dicts[i]
        new_base[keys] = tmpdict
    return new_base

def date_format(dt):
    dt=dt.split(" ")
    t = dt[1].split(":")
    tmpt = []
    for i in t:
        if len(str(i)) == 1:
            i = "0" + str(i)
        tmpt.append(i)
    t = tmpt
    if "-" in dt[0]:
        dt[0] = f'{dt[0].split("-")[2]}.{dt[0].split("-")[1]}.{dt[0].split("-")[0]}'
    dt = f'{dt[0]} {t[0]}:{t[1]}'
    return dt


# Раньше здесь была первая версия date_former(), возвращавшая кортеж
# (date, time). Она перекрывалась второй версией ниже (возвращает datetime),
# поэтому фактически была мёртвым кодом — удалена. Каноничная версия — ниже.

def name_format(name):
    if name:
        name = name.split(" ")
        tmp = ""
        for i in name:
            if len(i) != 0:
                tmp = tmp + f'{i} '
        tmp = tmp[:-1]
        return tmp
    return name

def bases_creator():
    a = fe.Files(logs=True, logtype="print")
    global f
    global base
    global lezbase
    global allbase
    global base_classes
    global lezbase_classes
    global allbase_classes
    global base_to_out
    global wp
    global points
    points = {}
    try:
        print("Укажите файл Stork (CSV)")
        office(a.read_file(f'{wp}/StorK.csv'))
    except Exception as e:
        print(f'Файл Stork (CSV) отсутствует, {e}')
    try:
        print("Укажите файл SIGUR (XLSX)")
        ceh(a.read_file(f'{wp}/SIGUR.xlsx'))
    except Exception as e:
        print(f'Файл SIGUR (XLSX) отсутствует, {e}')
    try:
        print("Укажите файл report (XLS)")
        hikvision(f'{wp}/report.xls')
    except Exception as e:
        print(f'Файл report (XLS) отсутствует, {e}')
    base = base_sort(base)
    try:
        print("Укажите файл ЛЭЗ")
        lez(a.read_file(f'{wp}/ЛЭЗ/lez.xlsx'))
    except Exception as e:
        print(f'Файл ЛЭЗ/lez.xlsx (xlsx) отсутствует, {e}')
    tmp = 0
    for i in lezbase.keys():
        if len(lezbase[i]) != 0 and not base.get(i):
            print(f'сотрудник   {i}  не найден')
            tmp += 1
    allbase = base.copy()
    for k, v in lezbase.items():
        if allbase.get(k):
            allbase[k] = {**allbase[k], **v}
        else:
            allbase[k] = v
    allbase = base_sort(allbase)
    for k in base.keys():
        base_classes[k] = {}
        for sk, sv in base[k].items():
            base_classes[k][date_former(sk)] = sv
    for k in lezbase.keys():
        lezbase_classes[k] = {}
        for sk, sv in lezbase[k].items():
            lezbase_classes[k][date_former(sk)] = sv
    for k in allbase.keys():
        allbase_classes[k] = {}
        for sk, sv in allbase[k].items():
            allbase_classes[k][date_former(sk)] = sv
    base_to_out = base_classes.copy()
    return base, lezbase

def find_emp(names, start_date, end_date, full=False, apply_fixed=True):  #FIXID_TIME(v0.1)
    global rebuild_base
    global full_upload
    full_upload = {}
    rebuild_base = {}
    base, lez = bases_creator()
    #input(base)
    full_upload = base.copy()
    if full:
        for k, v in base.items():
            if lez.get(k) != None:
                for k1, v1 in lez.get(k).items():
                    full_upload[k][k1] = v1
    tmp = {}
    if len(names) ==0:
        names = list(allbase.keys())
        for i in list(lez.keys()):
            if i not in names:
                names.append(i)
    for i in names:
        #print(i)
        if base.get(i):
            for k, v in base.get(i).items():
                #if date_checker(start_date, end_date, k):
                if not tmp.get(i):
                    tmp[i] = {}
                tmp[i][k] = v
    base = tmp.copy()
    tmp = {}
    for i in names:
        if lez.get(i):
            for k, v in lez.get(i).items():
                #if date_checker(start_date, end_date, k):
                if not tmp.get(i):
                    tmp[i] = {}
                tmp[i][k] = v
    lez = tmp.copy()
    for names, events in lez.items():
        for date, event in events.items():
            found = False
            if base.get(names):
                for basedate, baseevent in base[names].items():
                    if date_checker(basedate.split(" ")[0], basedate.split(" ")[0], date.split(" ")[0]):
                        found = True
                        break
                if not found:
                    if type(base.get(names)) !=dict:
                        base[names] = {}
                    base[names][date] = f'{lez.get(names).get(date)}(ЛЭЗ)'
            elif lez.get(names):
                if not found:
                    if type(base.get(names)) !=dict:
                        base[names] = {}
                    base[names][date] = f'{lez.get(names).get(date)}(ЛЭЗ)'
    base = base_sort(base)
    if full:
        full_upload = base_sort(full_upload)
    new_base={}
    for k, v in base.items():
        rebuild_base[k] = []
        new_base[k] = {}
        alltime = datetime(year=2000, month=1, day =1, hour=0, minute=0)
        entered = False
        now = list(v.keys())[0]
        start_time = False
        end_time = False
        tmpdict = {}
        #print(1, v.items())
        v["01.01.2021 00:00"] = "Вход"
        for date, event in v.copy().items():
            #print(2, date, event)
            #print(now)
            if date_checker(now.split(" ")[0], now.split(" ")[0], date):
                #new_base[k][date] = base.get(k).get(date)
                tmpdict[date] = base.get(k).get(date)
                #print(3, date, event)
                if event.lower() == "вход" and entered == False:
                    entered = True
                    start_time = date
                if event.lower() == "выход":
                    end_time = date
            else:
                sumtime = " "
                if not start_time:
                    try:
                        for rezerv_date, rezerv_event in lez.get(k).items():
                            if date_checker(now.split(" ")[0], now.split(" ")[0], rezerv_date) and rezerv_event == "Вход":
                                entered = True
                                start_time = rezerv_date
                                #new_base[k][rezerv_date] = f'{lez.get(k).get(rezerv_date)}(ЛЭЗ)'
                                tmpdict[rezerv_date] = f'{lez.get(k).get(rezerv_date)}(ЛЭЗ)'
                                break
                    except:
                        pass
                if not end_time:
                    #print(now)
                    try:
                        for rezerv_date, rezerv_event in lez.get(k).items():
                            if date_checker(now.split(" ")[0], now.split(" ")[0], rezerv_date) and rezerv_event == "Выход":
                                end_time = rezerv_date
                                #new_base[k][rezerv_date] = f'{lez.get(k).get(rezerv_date)}(ЛЭЗ)'
                                tmpdict[rezerv_date] = f'{lez.get(k).get(rezerv_date)}(ЛЭЗ)'
                    except:
                        pass
                tmpdict = base_sort({k: tmpdict})
                for x, y in tmpdict[k].copy().items():
                    new_base[k][x] = y
                # === Коррекция фиксированного времени прихода ===
                # Делается ПОСЛЕ определения start_time (включая резерв из ЛЭЗ),
                # но ДО расчёта sumtime - чтобы итог часов учитывал подмену.
                # При apply_fixed=False (расчёт для листа "Выгрузка" без фикса)
                # подстановка пропускается - получаем результат как у базового
                # SCUD.py.
                start_fixed = False  #FIXID_TIME(v0.1)
                original_start = start_time  #FIXID_TIME(v0.1)
                if apply_fixed:  #FIXID_TIME(v0.1)
                    try:  #FIXID_TIME(v0.1)
                        start_time, start_fixed = apply_fixed_start_time(  #FIXID_TIME(v0.1)
                            start_time, k, fixed_start_employees  #FIXID_TIME(v0.1)
                        )  #FIXID_TIME(v0.1)
                    except NameError:  #FIXID_TIME(v0.1)
                        # На случай прямого вызова find_emp без start()
                        pass  #FIXID_TIME(v0.1)
                # ================================================
                if start_time and end_time:
                    new_base[k][f'Итого на {now.split(" ")[0]}'] = round((date_former(end_time) - date_former(start_time)).total_seconds()/60/60, 2)
                    alltime = alltime + (date_former(end_time) - date_former(start_time))
                    sumtime = round((date_former(end_time) - date_former(start_time)).total_seconds()/60/60, 2)
                if start_time == False:
                    start_time = " -"
                if end_time == False:
                    end_time = " -"
                rebuild_base[k].append({
                    "date": now.split(" ")[0],
                    "start": start_time.split(" ")[-1],
                    "end": end_time.split(" ")[-1],
                    "sumtime": sumtime,
                    "start_fixed": start_fixed,  #FIXID_TIME(v0.1)
                    "original_start": original_start.split(" ")[-1] if start_fixed else None,  #FIXID_TIME(v0.1)
                })
                start_time = False
                end_time = False
                entered = False
                now = date
                tmpdict = {}
                tmpdict[date] = base.get(k).get(date)
                if event.lower() == "вход":
                    entered = True
                    start_time = date
                if event.lower() == "выход":
                    end_time = date
        hr = (alltime - datetime(year=2000, month=1, day=1, hour=0, minute=0))
        hr = round(hr.total_seconds()/60/60, 2)
        #hr = float(hr.days*24) + float(hr.hour) + float(hr.minute/60)
        new_base[k]["Итого за всё время"] = (hr)
        rebuild_base[k].append({"date": "-", "start": "-", "end": "Итого;", "sumtime": hr})
    return new_base

    #return base, lez

def date_checker(start_date, end_date, date):
    start_date = start_date.split(".")
    end_date = end_date.split(".")
    date = date.split(" ")[0].split(".")
    for i in range(0, 3):
        if date[i] >= start_date[i] and date[i] <= end_date[i]:
            pass
        else:
            return False
    return True

def date_former(indate):
    try:
        indatem = str(indate)
        indatem = indate.split(" ")
        indatet = indatem[1].split(":")
        indatem = indatem[0]
        indatem = indatem.split(".")
        return datetime(day=int(indatem[0]), month=int(indatem[1]), year=int(indatem[2]), hour=int(indatet[0]), minute=int(indatet[1]))
    except Exception as e:
        print("date_former", e)
        return indate

def old_xls_reader(filename):
    letters = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T",
               "U", "V", "W", "X", "Y", "Z",
               "AA", "AB", "AC", "AD", "AE", "AF", "AG", "AH", "AI", "AJ", "AK", "AL", "AM", "AN", "AO", "AP", "AQ",
               "AR", "AS", "AT", "AU", "AV", "AW", "AX", "AY", "AZ"]
    with open(filename, encoding="utf-8") as f:
        table = f.readlines()
        xml = ""
        for i in table:
            xml += str(i)
        xml = xml.replace("\n", "").replace("\'", "")
        data = str(xml).split('<table class="Detail2">')[-1].split("tr")
        trs = []
        for tr in data:
            if len(str(tr)) < 10:
                continue
            table = {}
            print(tr)
            count = 0
            for td in tr.split("<td"):#[1]:#.split('":@">')[1].replace("</td>", "")
                if len(str(td)) < 5 or "SECTION" in str(td) or "</body>" in td:
                    continue
                td = td.split(':@">')[1].replace("</td>", "")
                print(td)
                table[letters[count]] = td
                count += 1
                if count == 6:
                    break
            if table.get("F") != None:
                trs.append(table)
        return trs


def _build_общая_formats(workbook):
    """Создаёт и возвращает словарь форматов ячеек для листов
    "Общей выгрузки". Все форматы привязаны к переданному workbook,
    поэтому функцию надо вызывать внутри блока ExcelWriter."""
    base = {
        'text_wrap': True,
        'align': 'center',
        'valign': 'vcenter',
        'border_color': '#646464',
        'font_color': '#000000',
        'border': 1,
    }

    def fmt(**overrides):
        s = dict(base)
        s.update(overrides)
        return workbook.add_format(s)

    return {
        'white': fmt(bold=False, fg_color='#FFFFFF'),
        'yellow': fmt(bold=False, fg_color='#FFFF00'),
        # Жёлтый + жирный: ЛЭЗ-источник с подменой на фикс. время.
        'yellow_bold': fmt(bold=True, fg_color='#FFFF00'),
        'blue': fmt(bold=False, fg_color='#00FFFF'),
        'red': fmt(bold=False, fg_color='#FF0000'),
        # Зелёный (Excel "Good") + жирный: обычный источник с подменой
        # на фикс. время. Жирный нужен, чтобы при ч/б печати ячейка
        # отличалась от жёлтой ЛЭЗ-заливки (близкая яркость в серых).
        'fixed': fmt(bold=True, fg_color='#C6EFCE'),
    }


def _write_общая_sheet(writer, empty_df, sheet_name, rebuild_base_, tmp, formats):
    """Записывает один лист "Общей выгрузки".

    Логика подсветки колонки "Вход":
      - "-"                                -> красный
      - start_fixed=True И источник ЛЭЗ    -> жёлтый + жирный
      - start_fixed=True И обычный источник -> зелёный + жирный
      - источник ЛЭЗ                       -> жёлтый
      - иначе                              -> белый

    Колонка "Выход": ЛЭЗ -> жёлтый, "-" -> красный, иначе белый.
    """
    empty_df.to_excel(writer, sheet_name=sheet_name)
    worksheet = writer.sheets[sheet_name]
    worksheet.set_column(0, 1, 30)
    worksheet.set_column(2, 2, 6)
    worksheet.set_column(3, 3, 6)
    worksheet.set_column(4, 4, 6)
    worksheet.set_column(5, 5, 0)

    count = 1
    for name, events in rebuild_base_.items():
        worksheet.write(count, 0, "ФИО", formats['white'])
        worksheet.write(count, 1, "Дата", formats['white'])
        worksheet.write(count, 2, "Вход", formats['white'])
        worksheet.write(count, 3, "Выход", formats['white'])
        worksheet.write(count, 4, "0", formats['white'])
        count += 1
        start_count = count
        for ev in events:
            if "Итог" in ev["end"]:
                break
            worksheet.write(count, 0, name, formats['white'])
            if weekend(ev["date"]):
                worksheet.write(count, 1, ev["date"], formats['blue'])
            else:
                worksheet.write(count, 1, ev["date"], formats['white'])

            # Колонка "Вход".
            if ev["start"] == "-":
                worksheet.write(count, 2, ev["start"], formats['red'])
            elif ev.get("start_fixed"):
                # Время подменено на фикс. Источник определяем по ИСХОДНОМУ
                # времени (до подмены) - под новым ключом в tmp записи нет.
                orig = ev.get("original_start")
                orig_key = f'{ev["date"]} {orig}' if orig else ""
                from_lez = "ЛЭЗ" in tmp.get(name, {}).get(orig_key, "")
                fmt_in = formats['yellow_bold'] if from_lez else formats['fixed']
                worksheet.write(count, 2, ev["start"], fmt_in)
                if orig:
                    worksheet.write_comment(
                        count, 2,
                        f'Фактический приход: {orig}\nПодменено на фикс. время {ev["start"]}',
                        {'visible': False},
                    )
            elif "ЛЭЗ" in tmp.get(name, {}).get(f'{ev["date"]} {ev["start"]}', ""):
                worksheet.write(count, 2, ev["start"], formats['yellow'])
            else:
                worksheet.write(count, 2, ev["start"], formats['white'])

            # Колонка "Выход".
            if ev["end"] == "-":
                worksheet.write(count, 3, ev["end"], formats['red'])
            elif "ЛЭЗ" in tmp.get(name, {}).get(f'{ev["date"]} {ev["end"]}', ""):
                worksheet.write(count, 3, ev["end"], formats['yellow'])
            else:
                worksheet.write(count, 3, ev["end"], formats['white'])

            worksheet.write(
                count, 4,
                f'=ROUND((D{count+1}-C{count+1})*24, 2)-E${start_count}',
                formats['white'],
            )
            count += 1
        worksheet.write(count, 0, name, formats['white'])
        worksheet.write(count, 1, ' ', formats['white'])
        worksheet.write(count, 2, ' ', formats['white'])
        worksheet.write(count, 3, 'Итого:', formats['white'])
        worksheet.write(count, 4, f'=SUM(E{start_count+1}:E{count})', formats['white'])
        count += 1
        worksheet.write(count, 0, ' ')
        worksheet.write(count, 1, ' ')
        worksheet.write(count, 2, ' ')
        worksheet.write(count, 3, ' ')
        worksheet.write(count, 4, ' ')
        count += 1


# ============================================================================
# Нормализованная модель дня (SCUD v0.3)
# ----------------------------------------------------------------------------
# build_day_records() строит model.DayRecord ИЗ СЫРЫХ событий обеих систем
# (внутренние СКУД vs ЛЭЗ), РАЗДЕЛЬНО, с разбиением на смены по datetime —
# поэтому ночные смены (вход вечером, выход следующим утром) считаются
# корректно (а не как нулевые/отрицательные при разбиении по календарному
# дню, как в find_emp/v0.2). Дневные смены при этом не меняются.
# Легаси-листы «Выгрузка»/«Фиксированное время» по-прежнему пишутся из
# find_emp (не трогаем), а ВСЕ новые листы — из этих записей.
# to_rebuild_base() — обратный адаптер к легаси-структуре.
# ============================================================================
def _events_dt(per_system_base, name):
    """[(datetime, событие)] сотрудника по одной системе, отсортировано."""
    out = []
    d = (per_system_base or {}).get(name) or {}
    for key, ev in d.items():
        dt = date_former(key)
        if isinstance(dt, datetime):
            out.append((dt, str(ev)))
    out.sort(key=lambda x: x[0])
    return out


def _detect_shifts(events, gap_min, max_shift_min):
    """[(datetime, событие)] -> [(вход_dt, выход_dt|None)].

    Смена = непрерывное присутствие. Перерыв больше gap_min начинает новую
    смену (так ночные смены вечер->утро разделяются, а обед/короткая отлучка
    внутри смены — сливаются в один интервал, как первый-вход/последний-выход).
    Интервал длиннее max_shift_min обрезается (вероятно забыли отметить выход)."""
    # 1) элементарные пары вход->ближайший выход по времени
    pairs = []
    cur_in = None
    for dt, kind in events:
        k = str(kind).lower()
        if k.startswith("вход"):
            if cur_in is None:
                cur_in = dt
        elif k.startswith("выход"):
            if cur_in is not None:
                pairs.append([cur_in, dt])
                cur_in = None
    if cur_in is not None:
        pairs.append([cur_in, None])
    if not pairs:
        return []
    # 2) слияние соседних пар с маленьким разрывом (обед/отлучка внутри смены)
    merged = [pairs[0]]
    for p in pairs[1:]:
        last = merged[-1]
        if (last[1] is not None and p[0] is not None
                and (p[0] - last[1]).total_seconds() / 60.0 < gap_min):
            last[1] = p[1]
        else:
            merged.append(p)
    # 3) кап на длительность смены
    result = []
    for i, o in merged:
        if i and o and (o - i).total_seconds() / 60.0 > max_shift_min:
            o = None
        result.append((i, o))
    return result


def build_day_records(rebuild, internal_base, lez_base, ref=None,
                      fixed_employees=None, apply_fixed=True):
    """{ФИО: [DayRecord]} из сырых событий с разбиением на смены по datetime."""
    gap_min = model.THRESHOLDS.get("shift_gap_min", 300)
    max_min = model.THRESHOLDS.get("max_shift_min", 960)
    grace = model.THRESHOLDS["lateness_grace_min"]
    names = set(rebuild or {})            # тот же набор сотрудников, что в легаси
    records = {}
    for name in names:
        int_shifts = _detect_shifts(_events_dt(internal_base, name), gap_min, max_min)
        lez_events = _events_dt(lez_base, name)
        lez_shifts = _detect_shifts(lez_events, gap_min, max_min)
        # смены, индексированные по дате ВХОДА (первая смена дня)
        int_by_date, lez_by_date = {}, {}
        for i, o in int_shifts:
            int_by_date.setdefault(i.strftime("%d.%m.%Y"), (i, o))
        for i, o in lez_shifts:
            lez_by_date.setdefault(i.strftime("%d.%m.%Y"), (i, o))
        recs = []
        for ds in sorted(set(int_by_date) | set(lez_by_date),
                         key=lambda d: tuple(reversed(d.split(".")))):
            dr = model.DayRecord(name=name, date=ds)
            dr.is_weekend = weekend(ds)
            isin = int_by_date.get(ds)
            lzin = lez_by_date.get(ds)
            if isin:
                dr.int_entry = isin[0].strftime("%H:%M")
                dr.int_exit = isin[1].strftime("%H:%M") if isin[1] else None
            if lzin:
                dr.lez_entry = lzin[0].strftime("%H:%M")
                dr.lez_exit = lzin[1].strftime("%H:%M") if lzin[1] else None
            # Сырые отметки ЛЭЗ ВНУТРИ смены (для детекции отлучек > 30 мин).
            # Ограничиваем окном смены, иначе у ночных смен «утренний выход
            # одной смены + вечерний вход следующей» давал ложную отлучку.
            if lzin:
                w0, w1 = lzin[0], (lzin[1] or lzin[0])
                dr.lez_events = [(dt.strftime("%H:%M"), kind)
                                 for dt, kind in lez_events if w0 <= dt <= w1]

            # выбранные вход/выход: внутренняя система приоритетна, ЛЭЗ — резерв
            cin = isin[0] if isin else (lzin[0] if lzin else None)
            cin_src = "internal" if isin else ("LEZ" if lzin else None)
            if isin and isin[1] is not None:
                cout, cout_src = isin[1], "internal"
            elif lzin and lzin[1] is not None:
                cout, cout_src = lzin[1], "LEZ"
            else:
                cout, cout_src = None, None

            # фиксированное время прихода (как в find_emp): если пришёл раньше
            if apply_fixed and fixed_employees and cin is not None:
                s = cin.strftime("%d.%m.%Y %H:%M")
                news, changed = apply_fixed_start_time(s, name, fixed_employees)
                if changed:
                    dr.start_fixed = True
                    dr.original_start = cin.strftime("%H:%M")
                    cin = date_former(news)

            dr.entry = cin.strftime("%H:%M") if cin else None
            dr.exit = cout.strftime("%H:%M") if cout else None
            dr.entry_source = cin_src if cin else None
            dr.exit_source = cout_src if cout else None
            if cin and cout:
                dr.raw_hours = round((cout - cin).total_seconds() / 3600.0, 2)
                dr.worked_hours = dr.raw_hours

            # --- справочные вычисления ---
            if ref is not None:
                sched = ref.schedule(name)
                dr.dept = ref.dept(name)
                dr.cabinet = ref.cabinet(name)
                dr.schedule = sched
                dr.lez_controlled = ref.is_lez_controlled(name)
                window = ref.lunch.get(sched) if sched else None
                if dr.entry and dr.exit and window:
                    dr.lunch_deducted = compute.compute_lunch_hours(dr.entry, dr.exit, window)
                    dr.worked_hours = round(dr.raw_hours - dr.lunch_deducted, 2)
                shift_start = ref.shift_start.get(sched) if sched else None
                dr.lateness_min = compute.compute_lateness_min(dr.entry, shift_start, grace)
                shift_len = ref.shift_len.get(sched) if sched else None
                dr.day_norm = float(shift_len) if shift_len else 0.0
                dr.overtime_h = compute.compute_overtime_hours(dr.worked_hours, shift_len)
                dd = compute.parse_ddmmyyyy(ds)
                if dd is not None:
                    dr.absence = ref.absence_on(name, dd)
            recs.append(dr)

        # dual-tracking + отклонения
        has_int = any(r.int_entry or r.int_exit for r in recs)
        has_lez = any(r.lez_entry or r.lez_exit for r in recs)
        dual = has_int and has_lez
        for r in recs:
            r.dual_tracked = dual
            compute.evaluate_deviations(r, model.THRESHOLDS)
        records[name] = recs
    return records


def to_rebuild_base(records):
    """{ФИО: [DayRecord]} -> легаси rebuild_base для _write_общая_sheet()."""
    out = {}
    for name, recs in records.items():
        lst = []
        total = 0.0
        for dr in recs:
            if dr.entry and dr.exit:
                sumtime = dr.worked_hours
                total += dr.worked_hours
            else:
                sumtime = " "
            lst.append({
                "date": dr.date,
                "start": dr.entry if dr.entry else "-",
                "end": dr.exit if dr.exit else "-",
                "sumtime": sumtime,
                "start_fixed": dr.start_fixed,
                "original_start": dr.original_start,
            })
        lst.append({"date": "-", "start": "-", "end": "Итого;", "sumtime": round(total, 2)})
        out[name] = lst
    return out


def _self_check_records(rebuild, records):
    """Сверяет, что to_rebuild_base(build_day_records(...)) воспроизводит
    (date, start, end, start_fixed, original_start) исходного rebuild_base.
    Колонка часов в листе считается Excel-формулой, поэтому sumtime не
    сравниваем. Возвращает (ok, [сообщения о расхождениях])."""
    rebuilt = to_rebuild_base(records)
    msgs = []

    def days(lst):
        out = []
        for ev in lst:
            if isinstance(ev.get("end"), str) and "Итог" in ev["end"]:
                continue
            out.append((ev["date"], ev["start"], ev["end"],
                        bool(ev.get("start_fixed")), ev.get("original_start")))
        return out

    names = set(rebuild) | set(rebuilt)
    for name in names:
        a = days(rebuild.get(name, []))
        b = days(rebuilt.get(name, []))
        if a != b:
            msgs.append(f"{name}: {len(a)} vs {len(b)} записей; первое расхождение "
                        f"{next((x for x, y in zip(a, b) if x != y), '(длина)')}")
    return (not msgs), msgs


def start(workpath=None, automatic=False):
    f = fe.Files(logs=True, logtype="print")
    global base
    base = {}
    global lezbase
    lezbase = {}
    global allbase
    allbase = {}
    global base_classes
    base_classes = {}
    global lezbase_classes
    lezbase_classes = {}
    global allbase_classes
    allbase_classes = {}
    global wp
    global points
    points = {}
    global full_upload
    global fixed_start_employees  #FIXID_TIME(v0.1)
    fixed_start_employees = {}  #FIXID_TIME(v0.1)
    base_to_out = {}
    import csv
    #lez(f.file_selector())
    #exit()

    a = fe.Files(logs=True, logtype="print")
    wp = a.folder_selector(workpath)
    print(wp)
    # Загружаем список сотрудников с фиксированным временем прихода
    fixed_start_employees = load_fixed_start_employees(wp)  #FIXID_TIME(v0.1)
    # Справочные данные грузим ПОСЛЕ синхронизации справочника (ниже).
    global refdata_obj
    refdata_obj = refdata.RefData()
    #filesave = a.save_file()
        #file_writer = csv.writer(w_file, delimiter=";", lineterminator="\r")
        #file_writer.writerow(["ФИО", "Дата", "Событие"])
        #bases_creator()
    tmpb = list(allbase.keys())
    tmp = find_emp(tmpb, " ", " ")
    tmp = list(tmp.keys())
    emp_file_path = f'{wp}/ЛЭЗ/{EMPLOYEES_FILENAME}'  #FIXID_TIME(v0.1)
    emp, depl, emp_fixed_times = read_employees_file(emp_file_path, automatic)  #FIXID_TIME(v0.1)
    print(emp)
    newemp = []
    for i in tmp:
        if i not in emp and i not in depl:
            if not automatic:
                if str(input(f'Добавление {i} ?')) == "1":
                    newemp.append(i)
            else:
                newemp.append(i)
    for i in emp:
        newemp.append(i)
    emp = newemp
    write_employees_file(emp_file_path, emp, depl, emp_fixed_times)  #FIXID_TIME(v0.1)

    # --- Фаза 1: справочники ---
    # 1) Авто-сопровождение Справочник_сотрудников.xlsx: дописываем строки для
    #    новых ФИО (отдел/график пользователь заполняет сам), мигрируем
    #    фикс. время из Сотрудники.txt. Существующие данные не затираем.
    # 2) Создаём шаблоны норм/отсутствий/командировок, если их ещё нет.
    # 3) Перечитываем справочники в refdata_obj.
    try:
        refdata.sync_employee_reference(
            wp, emp + depl, emp_fixed_times, name_normalizer=name_format
        )
        refdata.ensure_templates(wp)
        refdata_obj = refdata.load_reference_data(wp, name_normalizer=name_format)
        # Пороги отклонений можно переопределить в ЛЭЗ/Настройки.json.
        overrides = refdata.load_settings(wp)
        if overrides:
            model.THRESHOLDS.update(overrides)
            print("Пороги переопределены из Настройки.json:", overrides)
    except Exception as e:
        print("Справочники: ошибка синхронизации", e)

    # Считаем «без фиксированного времени» - это поведение базового SCUD.py.
    tmp_no_fix = find_emp(emp, " ", " ", apply_fixed=False)  #FIXID_TIME(v0.1)
    rebuild_base_no_fix = rebuild_base  #FIXID_TIME(v0.1)
    # И «с фиксированным временем» - поведение этого скрипта.
    tmp = find_emp(emp, " ", " ", apply_fixed=True)  #FIXID_TIME(v0.1)
    rebuild_base_with_fix = rebuild_base  #FIXID_TIME(v0.1)

    # --- Фаза 0: построение нормализованной модели + самопроверка ---
    # Глобальные base (внутренние СКУД) и lezbase (ЛЭЗ) после find_emp хранят
    # отметки систем РАЗДЕЛЬНО — на их основе строим DayRecord. На вывод это
    # пока не влияет (листы по-прежнему пишутся из rebuild_base).
    global last_day_records
    try:
        last_day_records = build_day_records(
            rebuild_base_with_fix, base, lezbase, ref=refdata_obj,
            fixed_employees=fixed_start_employees, apply_fixed=True,
        )
        # Сверка с find_emp носит информационный характер: расхождения ожидаемы
        # для ночных смен (их build_day_records считает корректно, а find_emp —
        # по календарному дню, отсюда нули/минусы).
        ok, msgs = _self_check_records(rebuild_base_with_fix, last_day_records)
        print(f"DayRecord vs find_emp: расходится сотрудников {len(msgs)} "
              f"(ожидаемо для ночных смен)")
    except Exception as e:
        import traceback
        print("build_day_records: ошибка", e)
        traceback.print_exc()
        #print(type(tmp))
        #for k, v in tmp.items():
            #print(k)
            #name = k
            #file_writer.writerow([" ", " ", " "])
            #file_writer.writerow([" ", " ", " "])
            #file_writer.writerow([" ", " ", " "])
            #for dt, event in v.items():
                #print(name, dt, event)
                #file_writer.writerow([name, dt, event])
    print("OK")
    import pandas as pd

    # Пустой DataFrame только для регистрации листов через ExcelWriter -
    # реальное содержимое строится через worksheet.write ниже.
    empty_df = pd.DataFrame([[" "] * 5], columns=["ФИО", "Дата", "Вход", "Выход", "Итог"])  #FIXID_TIME(v0.1)
    with pd.ExcelWriter(f'{wp}/Общая выгрузка.xlsx', engine='xlsxwriter') as writer:
        workbook = writer.book
        formats = _build_общая_formats(workbook)  #FIXID_TIME(v0.1)
        # "Выгрузка" - поведение базового SCUD.py (без фикс. времени).
        _write_общая_sheet(  #FIXID_TIME(v0.1)
            writer, empty_df, "Выгрузка",  #FIXID_TIME(v0.1)
            rebuild_base_no_fix, tmp_no_fix, formats,  #FIXID_TIME(v0.1)
        )  #FIXID_TIME(v0.1)
        # "Фиксированное время" - с подменой времени прихода для
        # сотрудников из Сотрудники.txt (строки с "=ЧЧ:ММ").
        _write_общая_sheet(  #FIXID_TIME(v0.1)
            writer, empty_df, "Фиксированное время",  #FIXID_TIME(v0.1)
            rebuild_base_with_fix, tmp, formats,  #FIXID_TIME(v0.1)
        )  #FIXID_TIME(v0.1)
        # --- Фазы 3-4: аналитические листы ---
        try:
            import report
            rep_fmts = report.report_formats(workbook)
            used = {"Выгрузка", "Фиксированное время"}
            # Лист «Отклонения» — спорные записи для ручной проверки.
            n_dev = report.write_deviations_sheet(
                writer, last_day_records, rep_fmts, weekend_fn=weekend
            )
            used.add("Отклонения")
            # Добавляем записи-отсутствия (отпуск/больничный/командировка) за
            # дни без отметок — чтобы отсутствующие попадали в свод по норме.
            span = compute.date_span_of(last_day_records)
            n_abs = compute.inject_absence_records(
                last_day_records, refdata_obj, span, weekend_fn=weekend
            )
            if n_abs:
                print(f"Добавлено записей-отсутствий: {n_abs}")
            # Свёртка по сотрудникам за период (зачёт отсутствий — через будние
            # дни периода, чтобы полное отсутствие давало ~100% нормы).
            work_days = compute.count_working_days(span, weekend_fn=weekend)
            periods = compute.build_employee_periods(
                last_day_records, ref=refdata_obj, working_days=work_days
            )
            # Листы по отделам (авторазбивка табеля с обедом).
            dept_sheets = report.write_department_sheets(
                writer, last_day_records, rep_fmts, weekend_fn=weekend, used_names=used
            )
            # Бухгалтерия / Нормы / Опоздания и переработки.
            report.write_accounting_sheet(writer, periods, rep_fmts)
            report.write_norms_sheet(writer, periods, rep_fmts)
            report.write_late_overtime_sheet(writer, periods, rep_fmts)
            print(f"Аналитика: отклонений {n_dev}, листов по отделам {len(dept_sheets)}, "
                  f"сотрудников в своде {len(periods)}")
        except Exception as e:
            import traceback
            print("Аналитические листы: ошибка", e)
            traceback.print_exc()
    base = {}
    lezbase = {}
    allbase = {}
    base_classes = {}
    lezbase_classes = {}
    allbase_classes = {}
    points = {}
    base_to_out = {}
    import csv
    # lez(f.file_selector())
    # exit()
    print(wp)
    # filesave = a.save_file()
    # file_writer = csv.writer(w_file, delimiter=";", lineterminator="\r")
    # file_writer.writerow(["ФИО", "Дата", "Событие"])
    # bases_creator()
    tmpb = list(allbase.keys())
    tmp = find_emp(tmpb, " ", " ", True)
    tmp = list(tmp.keys())
    emp, depl, emp_fixed_times = read_employees_file(emp_file_path, automatic)  #FIXID_TIME(v0.1)
    print(emp)
    newemp = []
    for i in tmp:
        if i not in emp and i not in depl:
            if not automatic:
                if str(input(f'Добавление {i} ?')) == "1":
                    newemp.append(i)
            else:
                newemp.append(i)
    for i in emp:
        newemp.append(i)
    emp = newemp
    write_employees_file(emp_file_path, emp, depl, emp_fixed_times)  #FIXID_TIME(v0.1)

    tmp = find_emp(emp, " ", " ", True)
    r = []
    for name, events in full_upload.items():
        r.append([" ", " ", " ", " ", " "])
        r.append(["ФИО", "Дата", "Контроллер", "Событие"])
        for k, v in events.items():
            r.append([name, k, points.get(f'{name} {k}', "Неизвестно"), v, " "])

    df = pd.DataFrame(r, columns=["ФИО", "Дата", "Контроллер", "Событие", " "])
    with pd.ExcelWriter(f'{wp}/Полная выгрузка.xlsx', engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name="Выгрузка")
        workbook = writer.book
        worksheet = writer.sheets['Выгрузка']
        row_white_style = {'bold': False,
                           'text_wrap': True,
                           'align': 'center',
                           'valign': 'vcenter',
                           'fg_color': '#FFFFFF',
                           'border_color': '#646464',
                           'font_color': '#000000',
                           'border': 1
                           }
        row_white_format = workbook.add_format(row_white_style)
        row_yellow_style = {'bold': False,
                            'text_wrap': True,
                            'align': 'center',
                            'valign': 'vcenter',
                            'fg_color': '#FFFF00',
                            'border_color': '#646464',
                            'font_color': '#000000',
                            'border': 1
                            }
        row_yellow_format = workbook.add_format(row_yellow_style)
        row_blue_style = {'bold': False,
                          'text_wrap': True,
                          'align': 'center',
                          'valign': 'vcenter',
                          'fg_color': '#00FFFF',
                          'border_color': '#646464',
                          'font_color': '#000000',
                          'border': 1
                          }
        row_blue_format = workbook.add_format(row_blue_style)
        row_red_style = {'bold': False,
                         'text_wrap': True,
                         'align': 'center',
                         'valign': 'vcenter',
                         'fg_color': '#FF0000',
                         'border_color': '#646464',
                         'font_color': '#000000',
                         'border': 1
                         }
        row_red_format = workbook.add_format(row_red_style)
        writer.sheets["Выгрузка"].set_column(0, 2, 30)
        writer.sheets["Выгрузка"].set_column(3, 3, 6)
        writer.sheets["Выгрузка"].set_column(4, 4, 6)

        # for row in range(0, len(df)):
        # for col_num, value in enumerate(df.columns.values):
        count = 0
        for name, events in full_upload.items():
            worksheet.write(count, 0, "ФИО", row_white_format)
            worksheet.write(count, 1, "Дата", row_white_format)
            worksheet.write(count, 2, "Контроллер", row_white_format)
            worksheet.write(count, 3, "Событие", row_white_format)
            worksheet.write(count, 4, " ", row_white_format)
            count += 1
            start_count = count
            for dd, evnt in events.items():
                worksheet.write(count, 0, name, row_white_format)
                if weekend(dd):
                    worksheet.write(count, 1, dd, row_blue_format)
                else:
                    worksheet.write(count, 1, dd, row_white_format)
                worksheet.write(count, 2, points.get(f'{name} {dd}'), row_white_format)
                worksheet.write(count, 3, evnt, row_white_format)
                worksheet.write(count, 4, " ", row_white_format)

                count += 1
            worksheet.write(count, 0, f' .')
            worksheet.write(count, 1, f' .')
            worksheet.write(count, 2, f' .')
            worksheet.write(count, 3, f' .')
            worksheet.write(count, 4, f' .')

            count += 1


        #writer.sheets[str(date_former(datetime.now()))].set_column(4, 4, 12)
        #writer.sheets[str(date_former(datetime.now()))].set_column(5, 7, 25)
        #writer.sheets[str(date_former(datetime.now()))].set_column(8, 8, 10)
        #writer.sheets[str(date_former(datetime.now()))].set_column(9, 9, 0)
        #df.to_excel(writer, index=False, sheet_name="Выгрузка")

def weekend(md):
    try:
        md = md.split(".")
        tw = dw.get_calendar(f'{md[1]}.{md[2]}')
        #print(tw)
        for i in tw:
            if int(i[5]) == int(md[0]) or int(i[6]) == int(md[0]):
                return True
        return False
    except:
        return False


if __name__ == "__main__":
    #start("C:\\Users\\Orlov.S\\PycharmProjects\\pythonProject\\Time_report")
    start()



