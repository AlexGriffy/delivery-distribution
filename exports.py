"""Exports for checking the app's answer with outside tools."""

import io
from urllib.parse import quote_plus

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName

from transport import _num

NEOS_URL = "https://neos-server.org/neos/solvers/lp:HiGHS/LP.html"
SIMPLEX_URL = "https://www.zweigmedia.com/simplex/simplex.php"
WOLFRAM_MAX_VARS = 6


# --------------------------------------------------------------------------- #
# Plain-text forms for online solvers
# --------------------------------------------------------------------------- #
def _plain_names(p):
    """x11-style names when every index is one digit, otherwise x1, x2, ... in row order."""
    if p.m <= 9 and p.n <= 9:
        return [[f"x{i + 1}{j + 1}" for j in range(p.n)] for i in range(p.m)], False
    return [[f"x{i * p.n + j + 1}" for j in range(p.n)] for i in range(p.m)], True


def simplex_tool_text(p):
    """Input for the Finite Mathematics simplex tool (zweigmedia.com).

    That tool only takes <= and >=, so demand rows are written as >= and balanced
    supply rows as <=. With nonnegative costs the optimal cost is unchanged.
    """
    names, sequential = _plain_names(p)
    obj = " + ".join(f"{_num(p.cost[i][j])}{names[i][j]}" for i in range(p.m) for j in range(p.n))
    cons = [" + ".join(names[i]) + f" <= {_num(p.supply[i])}" for i in range(p.m)]
    cons += [" + ".join(names[i][j] for i in range(p.m)) + f" >= {_num(p.demand[j])}" for j in range(p.n)]
    text = f"Minimize c = {obj} subject to\n" + ",\n".join(cons)
    return text, sequential


def wolfram_url(p):
    """Wolfram|Alpha query link, or None when the problem is too big for its input box."""
    if p.m * p.n > WOLFRAM_MAX_VARS:
        return None
    letters = [c for c in "abcdfghjk"][: p.m * p.n]  # skip e and i (constants in Wolfram)
    v = [[letters[i * p.n + j] for j in range(p.n)] for i in range(p.m)]
    rel = "<=" if p.supply_sense == "<=" else "="
    obj = "+".join(f"{_num(p.cost[i][j])}{v[i][j]}" for i in range(p.m) for j in range(p.n))
    cons = ["+".join(v[i]) + f"{rel}{_num(p.supply[i])}" for i in range(p.m)]
    cons += ["+".join(v[i][j] for i in range(p.m)) + f"={_num(p.demand[j])}" for j in range(p.n)]
    cons += [f"{c}>=0" for c in letters]
    query = f"minimize {obj} subject to " + ", ".join(cons)
    legend = {v[i][j]: (p.sources[i], p.dests[j]) for i in range(p.m) for j in range(p.n)}
    return "https://www.wolframalpha.com/input?i=" + quote_plus(query), legend


# --------------------------------------------------------------------------- #
# Excel workbook with a ready-to-run Solver model
# --------------------------------------------------------------------------- #
HEAD = Font(bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", fgColor="1F3A5F")
VAR_FILL = PatternFill("solid", fgColor="FFF4CC")
KEY_FILL = PatternFill("solid", fgColor="DDEBF7")
THIN = Side(style="thin", color="B7B7B7")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _header(cell, text):
    cell.value = text
    cell.font, cell.fill = HEAD, HEAD_FILL
    cell.alignment = Alignment(horizontal="center", wrap_text=True)


def excel_workbook(p, sol):
    """Workbook whose 'Model' sheet carries Excel Solver settings, so Data > Solver > Solve just works."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Model"
    m, n = p.m, p.n
    col = lambda j: get_column_letter(2 + j)  # stores start in column B
    last = col(n - 1)

    ws["A1"] = "Transportation problem: Excel Solver check"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = ("Yellow cells are the decision variables (they start at 0). Go to Data > Solver and click "
                "Solve. The model is already filled in. If Solver is missing, see the Instructions sheet.")
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=max(6, n + 3))
    ws.row_dimensions[2].height = 45

    # --- cost table ---------------------------------------------------------
    r0 = 4
    ws.cell(r0, 1, "Cost per unit ($)").font = Font(bold=True)
    _header(ws.cell(r0 + 1, 1), "From \\ To")
    for j in range(n):
        _header(ws.cell(r0 + 1, 2 + j), p.dests[j])
    for i in range(m):
        ws.cell(r0 + 2 + i, 1, p.sources[i]).font = Font(bold=True)
        for j in range(n):
            c = ws.cell(r0 + 2 + i, 2 + j, p.cost[i][j])
            c.number_format, c.border = "#,##0.00", BOX
    cost_rng = f"$B${r0 + 2}:${last}${r0 + 1 + m}"

    # --- shipment table -----------------------------------------------------
    r1 = r0 + m + 4
    ws.cell(r1, 1, "Units shipped (decision variables)").font = Font(bold=True)
    _header(ws.cell(r1 + 1, 1), "From \\ To")
    for j in range(n):
        _header(ws.cell(r1 + 1, 2 + j), p.dests[j])
    tot_col, rel_col, sup_col = 2 + n, 3 + n, 4 + n
    _header(ws.cell(r1 + 1, tot_col), "Shipped")
    _header(ws.cell(r1 + 1, rel_col), "")
    _header(ws.cell(r1 + 1, sup_col), "Supply")
    for i in range(m):
        r = r1 + 2 + i
        ws.cell(r, 1, p.sources[i]).font = Font(bold=True)
        for j in range(n):
            c = ws.cell(r, 2 + j, 0)
            c.fill, c.border, c.number_format = VAR_FILL, BOX, "#,##0.##"
        ws.cell(r, tot_col, f"=SUM(B{r}:{last}{r})").number_format = "#,##0.##"
        ws.cell(r, rel_col, "<=" if p.supply_sense == "<=" else "=").alignment = Alignment(horizontal="center")
        ws.cell(r, sup_col, p.supply[i])
    ship_rng = f"$B${r1 + 2}:${last}${r1 + 1 + m}"
    rr, rrel, rd = r1 + 2 + m, r1 + 3 + m, r1 + 4 + m
    ws.cell(rr, 1, "Received").font = Font(bold=True)
    ws.cell(rrel, 1, "")
    ws.cell(rd, 1, "Demand").font = Font(bold=True)
    for j in range(n):
        L = col(j)
        ws.cell(rr, 2 + j, f"=SUM({L}{r1 + 2}:{L}{r1 + 1 + m})").number_format = "#,##0.##"
        ws.cell(rrel, 2 + j, "=").alignment = Alignment(horizontal="center")
        ws.cell(rd, 2 + j, p.demand[j])

    # --- objective + comparison --------------------------------------------
    ro = rd + 2
    ws.cell(ro, 1, "Total cost (minimize)").font = Font(bold=True)
    obj = ws.cell(ro, 2, f"=SUMPRODUCT({cost_rng},{ship_rng})")
    obj.number_format, obj.fill, obj.font = "$#,##0.00", KEY_FILL, Font(bold=True)
    ws.cell(ro + 1, 1, "App's optimal cost")
    ws.cell(ro + 1, 2, sol.objective if sol and sol.optimal else "n/a").number_format = "$#,##0.00"
    ws.cell(ro + 2, 1, "Difference (should be 0 after Solve)")
    ws.cell(ro + 2, 2, f"=IF(ISNUMBER(B{ro + 1}),ROUND(B{ro}-B{ro + 1},2),\"n/a\")").number_format = "$#,##0.00"

    ws.column_dimensions["A"].width = 34
    for j in range(n + 3):
        ws.column_dimensions[get_column_letter(2 + j)].width = 15

    # --- Solver model, stored the way Excel Solver saves it (hidden sheet-level names) ---
    sheet = "Model"
    solver = {
        "solver_adj": f"{sheet}!{ship_rng}",
        "solver_opt": f"{sheet}!$B${ro}",
        "solver_typ": "2",  # minimize
        "solver_val": "0",
        "solver_num": "2",
        "solver_lhs1": f"{sheet}!${get_column_letter(tot_col)}${r1 + 2}:${get_column_letter(tot_col)}${r1 + 1 + m}",
        "solver_rel1": "1" if p.supply_sense == "<=" else "2",  # 1 is <=, 2 is =
        "solver_rhs1": f"{sheet}!${get_column_letter(sup_col)}${r1 + 2}:${get_column_letter(sup_col)}${r1 + 1 + m}",
        "solver_lhs2": f"{sheet}!$B${rr}:${last}${rr}",
        "solver_rel2": "2",
        "solver_rhs2": f"{sheet}!$B${rd}:${last}${rd}",
        "solver_neg": "1",  # make unconstrained variables nonnegative
        "solver_eng": "2",  # Simplex LP
        "solver_lin": "1",
        "solver_ver": "3",
    }
    for name, ref in solver.items():
        ws.defined_names[name] = DefinedName(name, attr_text=ref, hidden=True)

    # --- App solution sheet ----------------------------------------------------
    s2 = wb.create_sheet("App solution")
    for k, h in enumerate(["From", "To", "Units", "Cost/unit", "Route cost"], start=1):
        _header(s2.cell(1, k), h)
    r = 2
    if sol and sol.optimal:
        for i in range(m):
            for j in range(n):
                q = sol.x[i][j]
                if q > 0:
                    s2.append([p.sources[i], p.dests[j], q, p.cost[i][j], q * p.cost[i][j]])
                    r += 1
        s2.cell(r + 1, 4, "Total").font = Font(bold=True)
        s2.cell(r + 1, 5, f"=SUM(E2:E{r - 1})").font = Font(bold=True)
    else:
        s2.cell(2, 1, f"The app found no optimal solution (status: {sol.status if sol else 'n/a'}).")
    for k, w in enumerate([30, 30, 10, 12, 14], start=1):
        s2.column_dimensions[get_column_letter(k)].width = w
    for row in s2.iter_rows(min_row=2, min_col=4, max_col=5):
        for c in row:
            c.number_format = "$#,##0.00"

    # --- Instructions sheet ------------------------------------------------------
    s3 = wb.create_sheet("Instructions")
    lines = [
        "How to verify the app's answer",
        "",
        "Excel for Windows or Mac (desktop):",
        "1. If the Data tab has no Solver button, turn it on: File > Options > Add-ins > Manage: Excel Add-ins > Go > check 'Solver Add-in'.",
        "   (Mac: Tools > Excel Add-ins > check 'Solver Add-in'.)",
        "2. Open the Model sheet and click Data > Solver. The objective, variable cells and constraints are already filled in.",
        "3. Click Solve, then Keep Solver Solution. Compare 'Total cost' with 'App's optimal cost'. The difference should be $0.00.",
        "   Some problems have more than one optimal plan, so the shipments can differ even when the cost matches.",
        "",
        "If the Solver box is empty (Excel on the web, LibreOffice, Google Sheets add-ons), enter it by hand:",
        f"   Set Objective: {solver['solver_opt'].split('!')[1]}   To: Min",
        f"   By Changing Variable Cells: {ship_rng}",
        f"   Constraint 1: {solver['solver_lhs1'].split('!')[1]} {'<=' if p.supply_sense == '<=' else '='} {solver['solver_rhs1'].split('!')[1]}   (supply)",
        f"   Constraint 2: {solver['solver_lhs2'].split('!')[1]} = {solver['solver_rhs2'].split('!')[1]}   (demand)",
        "   Check 'Make Unconstrained Variables Non-Negative' and choose the 'Simplex LP' solving method.",
    ]
    for k, line in enumerate(lines, start=1):
        s3.cell(k, 1, line)
    s3["A1"].font = Font(bold=True, size=14)
    s3.column_dimensions["A"].width = 120

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
