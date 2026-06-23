def get_calendar(mydate):
    try:
        ves = False
        mydate=mydate.split(".")
        mydate[0] = int(mydate[0])
        mydate[1] = int(mydate[1])
        daydict={1: 31, 3:31, 4: 30, 5: 31, 6: 31, 7:30, 8:31, 9: 30, 10: 31, 11: 30, 12: 31}
        if mydate[1]%4 == 0:
            daydict[2] = 29
            ves = True
        else:
            daydict[2] = 28
        days = (mydate[1]-1)*365 + (mydate[1]-1)//4
        for i in range(1, mydate[0] + 1):
            days=days+daydict[i]
            #print(days)
        week = days//7*7
        week=days-week
        week=week+4
        if not ves and mydate[0] == 2:
            week +=3
        if ves and mydate[0] == 2:
            week +=2
        if mydate[0] > 2 and daydict[mydate[0]] == 30:
            week += 1
        if week > 7:
            week = week - 7
        #print(week)
        calendar = []
        tmp = []
        for i in range(1, week):
            tmp.append(" ")
        for i in range(1, daydict[mydate[0]] + 1):
            tmp.append(str(i))
            if len(tmp) == 7:
                calendar.append(tmp)
                tmp = []
        if len(tmp) != 7 and len(tmp) > 0:
            while len(tmp) != 7:
                tmp.append(" ")
            calendar.append(tmp)
        return calendar
    except:
        return None

print(get_calendar("07.2025"))