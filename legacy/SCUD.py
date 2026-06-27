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
                        print(row, len(row))
                        input()
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


def date_former(indate):
    indate = str(indate)
    indate = indate.split(" ")
    intime = indate[1]
    indate = indate[0]
    if "." in indate:
        indate = indate.split(".")
        indate = date(day=int(indate[0]), month=int(indate[1]), year=int(indate[2]))
        intime = intime.split(":")
        intime = time(hour=int(intime[0]), minute=int(intime[1])) #, second=int(intime[2])
    elif "-" in indate:
        indate = indate.split("-")
        indate = date(day=int(indate[2]), month=int(indate[1]), year=int(indate[0]))
        intime = intime.split(":")
        intime = time(hour=int(intime[0]), minute=int(intime[1]))
    return indate, intime

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

def find_emp(names, start_date, end_date, full=False):
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
                if start_time and end_time:
                    new_base[k][f'Итого на {now.split(" ")[0]}'] = round((date_former(end_time) - date_former(start_time)).total_seconds()/60/60, 2)
                    alltime = alltime + (date_former(end_time) - date_former(start_time))
                    sumtime = round((date_former(end_time) - date_former(start_time)).total_seconds()/60/60, 2)
                if start_time == False:
                    start_time = " -"
                if end_time == False:
                    end_time = " -"
                rebuild_base[k].append({"date": now.split(" ")[0], "start": start_time.split(" ")[-1], "end": end_time.split(" ")[-1], "sumtime": sumtime})
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
    base_to_out = {}
    import csv
    #lez(f.file_selector())
    #exit()

    a = fe.Files(logs=True, logtype="print")
    wp = a.folder_selector(workpath)
    print(wp)
    #filesave = a.save_file()
        #file_writer = csv.writer(w_file, delimiter=";", lineterminator="\r")
        #file_writer.writerow(["ФИО", "Дата", "Событие"])
        #bases_creator()
    tmpb = list(allbase.keys())
    tmp = find_emp(tmpb, " ", " ")
    tmp = list(tmp.keys())
    emp = []
    depl = []
    try:
        with open(f'{wp}/ЛЭЗ/Сотрудники.txt', encoding="utf_8_sig") as f:
            for i in f.readlines():
                if "!" not in i:
                    emp.append(i.replace("\n", ""))
                elif "!-" in i:
                    #input(f'Требуется удалить {i}')
                    i = i.replace("!-", "")
                    depl.append(i.replace("\n", ""))
                elif "!" in i:
                    if not automatic:
                        input(f'Требуется удалить {i}')
                    i = i.replace("!", "")
                    depl.append(i.replace("\n", ""))
        print(emp)
    except Exception as e:
        print(str(e))
    newemp = []
    #input(tmp)
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
    with open(f'{wp}/ЛЭЗ/Сотрудники.txt', "w", encoding="utf_8_sig") as f:
        for i in emp:
            f.write(f'{i}\n')
        for i in depl:
            f.write(f'!{i}\n')


    tmp = find_emp(emp, " ", " ")
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
    #input(points)
    import pandas as pd
    r = []
    for name, events in rebuild_base.items():
        r.append([" ", " ", " ", " ", " "])
        r.append(["ФИО", "Дата", "Вход", "Выход", " "])
        print(name, events)
        for i in events:
            r.append([name, i["date"], i["start"], i["end"], i["sumtime"]])

    df = pd.DataFrame(r, columns=["ФИО", "Дата", "Вход", "Выход", "Итог"])
    with pd.ExcelWriter(f'{wp}/Общая выгрузка.xlsx', engine='xlsxwriter') as writer:
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
        writer.sheets["Выгрузка"].set_column(0, 1, 30)
        writer.sheets["Выгрузка"].set_column(2, 2, 6)
        writer.sheets["Выгрузка"].set_column(3, 3, 6)
        writer.sheets["Выгрузка"].set_column(4, 4, 6)
        writer.sheets["Выгрузка"].set_column(5, 5, 0)
        #for row in range(0, len(df)):
            #for col_num, value in enumerate(df.columns.values):
        count = 1
        for name, events in rebuild_base.items():
            worksheet.write(count, 0, "ФИО", row_white_format)
            worksheet.write(count, 1, "Дата", row_white_format)
            worksheet.write(count, 2, "Вход", row_white_format)
            worksheet.write(count, 3, "Выход", row_white_format)
            worksheet.write(count, 4, "0", row_white_format)
            count+=1
            start_count = count
            for ev in events:
                if "Итог" in ev["end"]:
                    break
                worksheet.write(count, 0, name, row_white_format)
                if weekend(ev["date"]):
                    worksheet.write(count, 1, ev["date"], row_blue_format)
                else:
                    worksheet.write(count, 1, ev["date"], row_white_format)
                if ev["start"] =="-":
                    worksheet.write(count, 2, ev["start"], row_red_format)
                elif "ЛЭЗ" in tmp[name][f'{ev["date"]} {ev["start"]}']:
                    worksheet.write(count, 2, ev["start"], row_yellow_format)
                else:
                    worksheet.write(count, 2, ev["start"], row_white_format)
                if ev["end"] =="-":
                    worksheet.write(count, 3, ev["end"], row_red_format)
                elif "ЛЭЗ" in tmp[name][f'{ev["date"]} {ev["end"]}']:
                    worksheet.write(count, 3, ev["end"], row_yellow_format)
                else:
                    worksheet.write(count, 3, ev["end"], row_white_format)
                #worksheet.conditional_format(f'E{count}:E{count}', {'type': 'formula',
                #                                       'criteria': f'=ROUND((D{count}-C{count})*24, 2)',
                #                                       'format': row_white_format})
                worksheet.write(count, 4, f'=ROUND((D{count+1}-C{count+1})*24, 2)-E${start_count}', row_white_format)
                count +=1
            worksheet.write(count, 0, name, row_white_format)
            worksheet.write(count, 1, f' ', row_white_format)
            worksheet.write(count, 2, f' ', row_white_format)
            worksheet.write(count, 3, f'Итого:', row_white_format)
            worksheet.write(count, 4, f'=SUM(E{start_count+1}:E{count})', row_white_format)
            count+=1
            worksheet.write(count, 0, f' ')
            worksheet.write(count, 1, f' ')
            worksheet.write(count, 2, f' ')
            worksheet.write(count, 3, f' ')
            worksheet.write(count, 4, f' ')
            count+=1
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
    emp = []
    depl = []
    try:
        with open(f'{wp}/ЛЭЗ/Сотрудники.txt', encoding="utf_8_sig") as f:
            for i in f.readlines():
                if "!" not in i:
                    emp.append(i.replace("\n", ""))
                elif "!-" in i:
                    # input(f'Требуется удалить {i}')
                    i = i.replace("!-", "")
                    depl.append(i.replace("\n", ""))
                elif "!" in i:
                    if not automatic:
                        input(f'Требуется удалить {i}')
                    i = i.replace("!", "")
                    depl.append(i.replace("\n", ""))
        print(emp)
    except Exception as e:
        print(str(e))
    newemp = []
    # input(tmp)
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
    with open(f'{wp}/ЛЭЗ/Сотрудники.txt', "w", encoding="utf_8_sig") as f:
        for i in emp:
            f.write(f'{i}\n')
        for i in depl:
            f.write(f'!{i}\n')

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



