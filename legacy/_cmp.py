"""Compare two .xlsx workbooks cell-by-cell (values + formulas).

Usage: python _cmp.py "<a.xlsx>" "<b.xlsx>"
Exit code 0 if identical (cell values/formulas), 1 otherwise.
"""
import sys
import openpyxl


def cells(path):
    wb = openpyxl.load_workbook(path, data_only=False)
    out = {}
    for ws in wb.worksheets:
        d = {}
        for row in ws.iter_rows():
            for c in row:
                if c.value is not None:
                    d[c.coordinate] = c.value
        out[ws.title] = d
    wb.close()
    return out


def main():
    a = cells(sys.argv[1])
    b = cells(sys.argv[2])
    fatal = []      # diffs in shared sheets, or sheets present in A but missing in B
    extra = []      # additive sheets only in B (not fatal)
    sheets = sorted(set(a) | set(b))
    for s in sheets:
        if s not in a:
            extra.append(s)
            continue
        if s not in b:
            fatal.append(f"sheet MISSING in B: {s}")
            continue
        da, db = a[s], b[s]
        for k in sorted(set(da) | set(db)):
            va, vb = da.get(k), db.get(k)
            if va != vb:
                fatal.append(f"[{s}!{k}] A={va!r} B={vb!r}")

    if extra:
        print("note: additive sheets only in B (ignored):", extra)
    if not fatal:
        print("IDENTICAL (shared sheets match cell values/formulas)")
        sys.exit(0)
    print(f"DIFFERENCES: {len(fatal)}")
    for d in fatal[:40]:
        print(" ", d)
    if len(fatal) > 40:
        print(f"  ... and {len(fatal) - 40} more")
    sys.exit(1)


if __name__ == "__main__":
    main()
