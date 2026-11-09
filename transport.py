"""Transportation problem: build the LP from a scenario, solve it, and render it as LaTeX."""

from dataclasses import dataclass, field

import pulp

from cities import haversine_miles

DUMMY_SOURCE = "Unmet demand (dummy warehouse)"
DUMMY_DEST = "Unused supply (dummy store)"
TOL = 1e-6


# --------------------------------------------------------------------------- #
# Scenario -> problem data
# --------------------------------------------------------------------------- #
def route_miles(w, s):
    return haversine_miles(w["lat"], w["lon"], s["lat"], s["lon"])


def default_cost(scn, w, s):
    return round(scn["cost_per_mile"] * route_miles(w, s), 2)


def route_cost(scn, w, s):
    """Manual override if the user typed one, otherwise rate x distance."""
    return scn["cost_overrides"].get(f"{w['id']}|{s['id']}", default_cost(scn, w, s))


@dataclass
class TransportProblem:
    sources: list
    dests: list
    supply: list
    demand: list
    cost: list  # cost[i][j]
    supply_sense: str = "<="  # "<=" (supply is a limit) or "=" (balanced textbook form)
    dummy_source: bool = False
    dummy_dest: bool = False

    @property
    def m(self):
        return len(self.sources)

    @property
    def n(self):
        return len(self.dests)

    @property
    def real_m(self):
        return self.m - self.dummy_source

    @property
    def real_n(self):
        return self.n - self.dummy_dest


def build_problem(scn, balance=False, shortage_penalty=0.0):
    """Turn a scenario dict into problem data. Returns None if there is nothing to solve.

    With balance=True the textbook trick is applied: a dummy store absorbs excess supply
    (cost 0), or a dummy warehouse covers a shortage (cost = shortage_penalty per unit),
    so every constraint becomes an equality.
    """
    ws, ss = scn["warehouses"], scn["stores"]
    if not ws or not ss:
        return None
    p = TransportProblem(
        sources=[w["name"] for w in ws],
        dests=[s["name"] for s in ss],
        supply=[float(w["supply"]) for w in ws],
        demand=[float(s["demand"]) for s in ss],
        cost=[[route_cost(scn, w, s) for s in ss] for w in ws],
    )
    if balance:
        gap = sum(p.supply) - sum(p.demand)
        if gap > TOL:
            p.dests.append(DUMMY_DEST)
            p.demand.append(gap)
            for row in p.cost:
                row.append(0.0)
            p.dummy_dest = True
        elif gap < -TOL:
            p.sources.append(DUMMY_SOURCE)
            p.supply.append(-gap)
            p.cost.append([float(shortage_penalty)] * p.n)
            p.dummy_source = True
        p.supply_sense = "="
    return p


# --------------------------------------------------------------------------- #
# Solve
# --------------------------------------------------------------------------- #
@dataclass
class Solution:
    status: str
    objective: float = None
    x: list = field(default_factory=list)  # x[i][j]
    supply_duals: list = field(default_factory=list)
    demand_duals: list = field(default_factory=list)
    reduced_costs: list = field(default_factory=list)

    @property
    def optimal(self):
        return self.status == "Optimal"


def build_lp(p):
    """PuLP model for the problem. Variable x_i_j = units shipped from source i to dest j."""
    prob = pulp.LpProblem("Transportation", pulp.LpMinimize)
    x = [[prob.add_variable(f"x_{i + 1}_{j + 1}", lowBound=0) for j in range(p.n)] for i in range(p.m)]
    prob += pulp.lpSum(p.cost[i][j] * x[i][j] for i in range(p.m) for j in range(p.n)), "Total_cost"
    for i in range(p.m):
        row = pulp.lpSum(x[i])
        prob += (row <= p.supply[i] if p.supply_sense == "<=" else row == p.supply[i]), f"supply_{i + 1}"
    for j in range(p.n):
        prob += pulp.lpSum(x[i][j] for i in range(p.m)) == p.demand[j], f"demand_{j + 1}"
    supply_cons = [prob.get_constraint_by_name(f"supply_{i + 1}") for i in range(p.m)]
    demand_cons = [prob.get_constraint_by_name(f"demand_{j + 1}") for j in range(p.n)]
    return prob, x, supply_cons, demand_cons


def _clean(v):
    v = round(v or 0.0, 6)
    return 0.0 if abs(v) < TOL else v


def solve(p):
    prob, x, supply_cons, demand_cons = build_lp(p)
    status = prob.solve(pulp.HiGHS(mip=False, msg=False)).status_str
    if status != "Optimal":
        return Solution(status=status)
    return Solution(
        status=status,
        objective=_clean(pulp.value(prob.objective)),
        x=[[_clean(v.varValue) for v in row] for row in x],
        supply_duals=[_clean(c.pi) for c in supply_cons],
        demand_duals=[_clean(c.pi) for c in demand_cons],
        reduced_costs=[[_clean(v.dj) for v in row] for row in x],
    )


def lp_file_text(p):
    """The model in CPLEX LP format (accepted by NEOS, GLPK, HiGHS, CPLEX, Gurobi, ...)."""
    import os
    import tempfile

    prob = build_lp(p)[0]
    fd, path = tempfile.mkstemp(suffix=".lp")
    os.close(fd)
    try:
        prob.writeLP(path)
        with open(path, encoding="utf-8") as f:
            return f.read()
    finally:
        os.remove(path)


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #
def fmt(v, money=False):
    """Compact number: 75 instead of 75.0, 12.5 instead of 12.50."""
    s = f"{v:,.2f}".rstrip("0").rstrip(".") if abs(v - round(v)) > TOL else f"{round(v):,}"
    return f"${s}" if money else s


def _num(v):
    """Number for LaTeX/plain-text equations (no thousands separators)."""
    return fmt(v).replace(",", "")


def var_tex(p, i, j):
    sep = "," if max(p.m, p.n) > 9 else ""
    return f"x_{{{i + 1}{sep}{j + 1}}}"


def tex_escape(s):
    for a, b in [("\\", r"\textbackslash "), ("{", r"\{"), ("}", r"\}"), ("_", r"\_"),
                 ("&", r"\&"), ("%", r"\%"), ("$", r"\$"), ("#", r"\#"), ("^", ""), ("~", "")]:
        s = s.replace(a, b)
    return s


# --------------------------------------------------------------------------- #
# LaTeX
# --------------------------------------------------------------------------- #
def latex_general(p):
    """Compact summation form of the model."""
    rel = r"\le" if p.supply_sense == "<=" else "="
    return rf"""
\begin{{aligned}}
\min\; Z \;=\; & \sum_{{i=1}}^{{{p.m}}} \sum_{{j=1}}^{{{p.n}}} c_{{ij}}\, x_{{ij}} \\[6pt]
\text{{subject to}}\quad
& \sum_{{j=1}}^{{{p.n}}} x_{{ij}} \;{rel}\; s_i, && i = 1,\dots,{p.m} \quad \text{{(supply)}} \\
& \sum_{{i=1}}^{{{p.m}}} x_{{ij}} \;=\; d_j, && j = 1,\dots,{p.n} \quad \text{{(demand)}} \\
& x_{{ij}} \;\ge\; 0, && \forall\, i, j \quad \text{{(nonnegativity)}}
\end{{aligned}}
"""


def _wrap_terms(terms, per_line, first_prefix, cont_prefix=r"&\quad "):
    lines = [" + ".join(terms[k:k + per_line]) for k in range(0, len(terms), per_line)]
    out = first_prefix + lines[0]
    for line in lines[1:]:
        out += r" \\" + "\n" + cont_prefix + "+ " + line
    return out


def latex_expanded(p):
    """Every term and constraint written out with the scenario's numbers."""
    rel = r"\le" if p.supply_sense == "<=" else "="
    obj_terms = [f"{_num(p.cost[i][j])}\\,{var_tex(p, i, j)}" for i in range(p.m) for j in range(p.n)]
    rows = [_wrap_terms(obj_terms, 5, r"\min\; Z = {} & ")]
    rows.append(r"\\[6pt]")
    first = True
    for i in range(p.m):
        terms = [var_tex(p, i, j) for j in range(p.n)]
        prefix = r"\text{s.t.}\quad & " if first else "& "
        first = False
        rows.append(_wrap_terms(terms, 8, prefix) +
                    f" {rel} {_num(p.supply[i])} && \\text{{{tex_escape(p.sources[i])} supply}} \\\\")
    for j in range(p.n):
        terms = [var_tex(p, i, j) for i in range(p.m)]
        rows.append(_wrap_terms(terms, 8, "& ") +
                    f" = {_num(p.demand[j])} && \\text{{{tex_escape(p.dests[j])} demand}} \\\\")
    rows.append(r"& x_{ij} \ge 0 && \text{for all } i, j")
    return "\\begin{aligned}\n" + "\n".join(rows) + "\n\\end{aligned}"
