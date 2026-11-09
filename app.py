"""Interactive Delivery and Distribution Optimizer (Streamlit app).

Run locally with:  streamlit run app.py
"""

import copy
from datetime import datetime

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

import exports
import scenarios
import transport as tp
from cities import CITIES, nearest_city

st.set_page_config(page_title="Delivery & Distribution Optimizer", page_icon="🚚", layout="wide")

DEFAULT_PRESET = next(iter(scenarios.PRESETS))
WH_COLOR, ST_COLOR, ROUTE_COLOR = "#1f6feb", "#2da44e", "#e4572e"


# =========================================================================== #
# State helpers
# =========================================================================== #
def init_state():
    ss = st.session_state
    if "scn" not in ss:
        ss.scn = scenarios.load_preset(DEFAULT_PRESET)
        ss.ver = 0  # bumped whenever the scenario changes outside a widget, to reset editors
        ss.last_click = None
        ss.baseline = None


def bump():
    st.session_state.ver += 1


def scn():
    return st.session_state.scn


def unique_name(name, taken):
    name = (name or "").strip() or "Unnamed"
    if name not in taken:
        return name
    k = 2
    while f"{name} ({k})" in taken:
        k += 1
    return f"{name} ({k})"


def next_id(prefix):
    used = {n["id"] for n in scn()["warehouses"] + scn()["stores"]}
    k = 1
    while f"{prefix}{k}" in used:
        k += 1
    return f"{prefix}{k}"


def add_node(kind, lat, lon, name=None, qty=100.0):
    nodes = scn()[kind]
    prefix, qty_field, label = ("W", "supply", "Warehouse") if kind == "warehouses" else ("S", "demand", "Store")
    if not name:
        near = nearest_city(lat, lon)
        name = f"{near} {label.lower()}" if near else f"{label} {len(nodes) + 1}"
    nodes.append({"id": next_id(prefix), "name": unique_name(name, {n["name"] for n in nodes}),
                  "lat": round(lat, 4), "lon": round(lon, 4), qty_field: float(qty)})
    bump()


def load_scenario(new):
    st.session_state.scn = new
    bump()


# =========================================================================== #
# Widget callbacks
# =========================================================================== #
def cb_load_preset():
    load_scenario(scenarios.load_preset(st.session_state.preset_choice))


def cb_upload():
    f = st.session_state.get("uploader")
    if f is None:
        return
    try:
        load_scenario(scenarios.from_json(f.getvalue().decode("utf-8")))
        st.session_state.flash = ("success", f"Loaded scenario from {f.name}.")
    except Exception as e:  # noqa: BLE001 - show any parse problem to the user
        st.session_state.flash = ("error", f"Could not read {f.name}: {e}")


def cb_add_city():
    city = st.session_state.city_pick
    lat, lon = CITIES[city]
    kind = "warehouses" if st.session_state.city_kind == "Warehouse" else "stores"
    add_node(kind, lat, lon, name=city.split(",")[0], qty=st.session_state.city_qty)


def cb_node_editor(kind, key):
    """Apply st.data_editor changes (edits, deletions, additions) to the scenario."""
    delta = st.session_state[key]
    nodes = scn()[kind]
    qty = "supply" if kind == "warehouses" else "demand"
    fields = {"Name": "name", "Supply": qty, "Demand": qty, "Latitude": "lat", "Longitude": "lon"}
    for row, changes in delta["edited_rows"].items():
        node = nodes[int(row)]
        for col, val in changes.items():
            if val is None or col not in fields:
                continue
            f = fields[col]
            if f == "name":
                node["name"] = unique_name(val, {n["name"] for n in nodes if n is not node})
            elif f == qty:
                node[f] = max(0.0, float(val))
            else:
                node[f] = float(val)
    for row in sorted(delta["deleted_rows"], reverse=True):
        removed = nodes.pop(int(row))
        scn()["cost_overrides"] = {k: v for k, v in scn()["cost_overrides"].items()
                                   if removed["id"] not in k.split("|")}
    for row in delta["added_rows"]:
        if row.get("Latitude") is None or row.get("Longitude") is None:
            st.session_state.flash = ("warning", "New rows need a latitude and longitude. Clicking the map "
                                                 "or using 'Add from city list' is easier.")
            continue
        add_node(kind, row["Latitude"], row["Longitude"], name=row.get("Name"),
                 qty=row.get("Supply", row.get("Demand")) or 0)
    bump()


def cb_cost_editor(key):
    delta = st.session_state[key]
    ws, ss_ = scn()["warehouses"], scn()["stores"]
    by_name = {s["name"]: s for s in ss_}
    for row, changes in delta["edited_rows"].items():
        w = ws[int(row)]
        for col, val in changes.items():
            s = by_name.get(col)
            if s is None:
                continue
            k = f"{w['id']}|{s['id']}"
            if val is None or abs(float(val) - tp.default_cost(scn(), w, s)) < 1e-9:
                scn()["cost_overrides"].pop(k, None)
            else:
                scn()["cost_overrides"][k] = max(0.0, float(val))
    bump()


def cb_reset_costs():
    scn()["cost_overrides"] = {}
    bump()


def cb_save_baseline(problem, sol):
    st.session_state.baseline = {
        "label": f"Baseline saved {datetime.now():%I:%M:%S %p}",
        "scn": copy.deepcopy(scn()),
        "problem": problem,
        "sol": sol,
    }


# =========================================================================== #
# Solving (cached on the problem data, so re-runs are free)
# =========================================================================== #
@st.cache_data(show_spinner=False)
def solve_cached(problem):
    return tp.solve(problem)


# =========================================================================== #
# Map
# =========================================================================== #
def build_map(s, problem, sol):
    m = folium.Map(location=[39.5, -98.35], zoom_start=4, control_scale=True)
    ws, ss_ = s["warehouses"], s["stores"]

    if sol is not None and sol.optimal:
        flows = [(i, j, sol.x[i][j]) for i in range(problem.real_m) for j in range(problem.real_n)
                 if sol.x[i][j] > 0]
        qmax = max((q for *_, q in flows), default=1)
        for i, j, q in flows:
            w, st_ = ws[i], ss_[j]
            c = problem.cost[i][j]
            folium.PolyLine(
                [(w["lat"], w["lon"]), (st_["lat"], st_["lon"])],
                color=ROUTE_COLOR, weight=2 + 10 * q / qmax, opacity=0.75,
                tooltip=f"{w['name']} → {st_['name']}: {tp.fmt(q)} units × {tp.fmt(c, True)} = {tp.fmt(q * c, True)}",
            ).add_to(m)
            mid = ((w["lat"] + st_["lat"]) / 2, (w["lon"] + st_["lon"]) / 2)
            folium.Marker(mid, icon=folium.DivIcon(
                icon_size=(0, 0),
                html=(f'<div style="transform:translate(-50%,-50%);display:inline-block;white-space:nowrap;'
                      f'background:#fff;border:1px solid {ROUTE_COLOR};border-radius:10px;padding:1px 6px;'
                      f'font:600 11px sans-serif;color:#333">{tp.fmt(q)}</div>'),
            )).add_to(m)

    unmet = {}
    if sol is not None and sol.optimal and problem.dummy_source:
        unmet = {j: sol.x[problem.m - 1][j] for j in range(problem.real_n) if sol.x[problem.m - 1][j] > 0}

    for w in ws:
        folium.Marker(
            (w["lat"], w["lon"]),
            tooltip=f"🏭 {w['name']}: supply {tp.fmt(w['supply'])}",
            icon=folium.Icon(color="blue", icon="industry", prefix="fa"),
        ).add_to(m)
    for j, s_ in enumerate(ss_):
        short = unmet.get(j)
        tip = f"🛒 {s_['name']}: demand {tp.fmt(s_['demand'])}"
        if short:
            tip += f" ({tp.fmt(short)} unmet)"
        folium.Marker(
            (s_["lat"], s_["lon"]), tooltip=tip,
            icon=folium.Icon(color="red" if short else "green", icon="shopping-cart", prefix="fa"),
        ).add_to(m)
    return m


# =========================================================================== #
# Page
# =========================================================================== #
init_state()
S = scn()
ver = st.session_state.ver

# ---------------- Sidebar ---------------- #
with st.sidebar:
    st.header("Scenario")
    st.selectbox("Example scenarios", list(scenarios.PRESETS), key="preset_choice")
    st.button("Load example", key="load_btn", on_click=cb_load_preset, width="stretch")
    st.file_uploader("Open a saved scenario (.json)", type="json", key="uploader", on_change=cb_upload)
    st.download_button("💾 Save scenario (.json)", scenarios.to_json(S), file_name="scenario.json",
                       mime="application/json", width="stretch")

    st.header("Add locations")
    click_mode = st.radio("Clicking the map adds a…", ["Nothing", "Warehouse", "Store"], horizontal=True)
    with st.expander("…or add from a city list"):
        st.selectbox("City", list(CITIES), key="city_pick")
        st.radio("Type", ["Warehouse", "Store"], horizontal=True, key="city_kind")
        st.number_input("Supply / demand (units)", min_value=0.0, value=100.0, step=10.0, key="city_qty")
        st.button("Add", key="add_city_btn", on_click=cb_add_city, width="stretch")

    st.header("Shipping costs")
    S["cost_per_mile"] = st.number_input(
        "Default cost ($ per unit per mile)", min_value=0.0, value=float(S["cost_per_mile"]),
        step=0.01, format="%.3f", key=f"rate_{ver}",
        help="Every route starts at this rate × straight-line distance. Edit individual routes "
             "in the 'Shipping costs' tab.",
    )
    n_over = len(S["cost_overrides"])
    st.button(f"Reset {n_over} manual cost edit(s)", on_click=cb_reset_costs, disabled=n_over == 0,
              width="stretch")

    st.header("Model options")
    balance = st.checkbox(
        "Balance with a dummy node (textbook form)", key="balance",
        help="Adds a dummy store that takes any excess supply at $0, or a dummy warehouse that covers "
             "any shortage at a penalty cost. All constraints then become equalities.",
    )
    penalty = 0.0
    if balance:
        penalty = st.number_input("Penalty per unit of unmet demand ($)", min_value=0.0, value=0.0, step=10.0,
                                  key="penalty")

# ---------------- Header ---------------- #
st.title("🚚 Delivery & Distribution Optimizer")
st.caption("Minimum-cost transportation plan from warehouses to stores, solved as a linear program "
           "(PuLP + HiGHS). Change anything and the plan re-solves instantly.")

if flash := st.session_state.pop("flash", None):
    getattr(st, flash[0])(flash[1])
if S.get("note"):
    st.info(S["note"], icon="📘")

problem = tp.build_problem(S, balance=balance, shortage_penalty=penalty)
sol = solve_cached(problem) if problem else None

tot_sup = sum(w["supply"] for w in S["warehouses"])
tot_dem = sum(s["demand"] for s in S["stores"])

# ---------------- Status row ---------------- #
c1, c2, c3, c4 = st.columns(4)
if sol is None:
    c1.metric("Status", "Add locations")
elif sol.optimal:
    real_cost = sum(problem.cost[i][j] * sol.x[i][j] for i in range(problem.real_m) for j in range(problem.real_n))
    shipped = sum(sol.x[i][j] for i in range(problem.real_m) for j in range(problem.real_n))
    routes = sum(1 for i in range(problem.real_m) for j in range(problem.real_n) if sol.x[i][j] > 0)
    c1.metric("Status", "✅ Optimal")
    c2.metric("Minimum total cost", tp.fmt(sol.objective, True),
              help="Objective value Z. With a dummy warehouse and a penalty, this includes the penalty cost.")
    c3.metric("Units shipped / demanded", f"{tp.fmt(shipped)} / {tp.fmt(tot_dem)}")
    c4.metric("Routes used", f"{routes} of {problem.real_m * problem.real_n}")
else:
    c1.metric("Status", f"❌ {sol.status}")

if sol is not None and not sol.optimal:
    if tot_dem > tot_sup + 1e-9:
        st.error(f"**No feasible plan.** Stores need **{tp.fmt(tot_dem)}** units but warehouses can supply only "
                 f"**{tp.fmt(tot_sup)}** (short by {tp.fmt(tot_dem - tot_sup)}). Every demand constraint is an "
                 f"equality, so they can't all be met. Add supply, cut demand, or turn on **Balance with a dummy "
                 f"node** in the sidebar to allow unmet demand.")
    else:
        st.error(f"The solver reported **{sol.status}**.")

# ---------------- Map ---------------- #
st.markdown(
    f"<span style='color:{WH_COLOR}'>●</span> Warehouse &nbsp; <span style='color:{ST_COLOR}'>●</span> Store &nbsp; "
    f"<span style='color:{ROUTE_COLOR}'>━</span> Shipment (line width and label = units) &nbsp; "
    f"<span style='color:#d63e2a'>●</span> Store with unmet demand"
    + ("" if click_mode == "Nothing" else f" &nbsp; | &nbsp; **Click the map to add a {click_mode.lower()}.**"),
    unsafe_allow_html=True,
)
ret = st_folium(build_map(S, problem, sol), key="map", height=520, use_container_width=True,
                returned_objects=["last_clicked"])
clicked = (ret or {}).get("last_clicked")
if clicked:
    pt = (round(clicked["lat"], 5), round(clicked["lng"], 5))
    if pt != st.session_state.last_click:
        st.session_state.last_click = pt
        if click_mode != "Nothing":
            add_node("warehouses" if click_mode == "Warehouse" else "stores", *pt)
            st.rerun()

# ---------------- Tabs ---------------- #
t_loc, t_cost, t_model, t_sol, t_ver, t_cmp = st.tabs(
    ["📍 Locations", "💲 Shipping costs", "🧮 LP model", "📦 Solution", "✅ Verify externally", "⚖️ Compare"])

# ---- Locations ---- #
with t_loc:
    st.caption("Edit cells directly. To delete a row, select it with the checkbox on the left and click the "
               "trash icon. Add new locations by clicking the map or using the sidebar.")
    gap = tot_sup - tot_dem
    bal_txt = ("balanced" if abs(gap) < 1e-9 else
               f"supply exceeds demand by {tp.fmt(gap)}" if gap > 0 else f"**demand exceeds supply by {tp.fmt(-gap)}**")
    st.markdown(f"Total supply **{tp.fmt(tot_sup)}** · Total demand **{tp.fmt(tot_dem)}** · {bal_txt}")
    left, right = st.columns(2)
    num = lambda label: st.column_config.NumberColumn(label, min_value=0.0, step=1.0)
    geo = {"Latitude": st.column_config.NumberColumn(format="%.4f", min_value=-90.0, max_value=90.0),
           "Longitude": st.column_config.NumberColumn(format="%.4f", min_value=-180.0, max_value=180.0)}
    with left:
        st.subheader("🏭 Warehouses")
        key = f"wh_editor_{ver}"
        st.data_editor(
            pd.DataFrame([{"Name": w["name"], "Supply": w["supply"], "Latitude": w["lat"], "Longitude": w["lon"]}
                          for w in S["warehouses"]], columns=["Name", "Supply", "Latitude", "Longitude"]),
            key=key, num_rows="dynamic", hide_index=True, width="stretch",
            column_config={"Supply": num("Supply"), **geo},
            on_change=cb_node_editor, args=("warehouses", key),
        )
    with right:
        st.subheader("🛒 Stores")
        key = f"st_editor_{ver}"
        st.data_editor(
            pd.DataFrame([{"Name": s["name"], "Demand": s["demand"], "Latitude": s["lat"], "Longitude": s["lon"]}
                          for s in S["stores"]], columns=["Name", "Demand", "Latitude", "Longitude"]),
            key=key, num_rows="dynamic", hide_index=True, width="stretch",
            column_config={"Demand": num("Demand"), **geo},
            on_change=cb_node_editor, args=("stores", key),
        )

# ---- Costs ---- #
with t_cost:
    if not problem:
        st.info("Add at least one warehouse and one store.")
    else:
        ws, ss_ = S["warehouses"], S["stores"]
        st.markdown(f"Each cell is the **cost per unit** to ship from a warehouse (row) to a store (column). "
                    f"Defaults are **{tp.fmt(S['cost_per_mile'], True)}/unit/mile × straight-line miles**. "
                    f"Type a number to override any route.")
        cost_df = pd.DataFrame([[tp.route_cost(S, w, s) for s in ss_] for w in ws],
                               index=[w["name"] for w in ws], columns=[s["name"] for s in ss_])
        key = f"cost_editor_{ver}_{S['cost_per_mile']}"
        st.data_editor(cost_df, key=key, width="stretch",
                       column_config={c: st.column_config.NumberColumn(c, min_value=0.0, format="$%.2f")
                                      for c in cost_df.columns},
                       on_change=cb_cost_editor, args=(key,))
        if S["cost_overrides"]:
            names = {n["id"]: n for n in ws + ss_}
            rows = []
            for k, v in S["cost_overrides"].items():
                wid, sid = k.split("|")
                if wid in names and sid in names:
                    rows.append({"Route": f"{names[wid]['name']} → {names[sid]['name']}",
                                 "Your cost": v, "Distance-based default": tp.default_cost(S, names[wid], names[sid])})
            st.markdown("**Manually edited routes**")
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                         column_config={"Your cost": st.column_config.NumberColumn(format="$%.2f"),
                                        "Distance-based default": st.column_config.NumberColumn(format="$%.2f")})
        with st.expander("Straight-line distances (miles)"):
            st.dataframe(pd.DataFrame([[round(tp.route_miles(w, s)) for s in ss_] for w in ws],
                                      index=[w["name"] for w in ws], columns=[s["name"] for s in ss_]),
                         width="stretch")

# ---- LP model ---- #
with t_model:
    if not problem:
        st.info("Add at least one warehouse and one store to generate the model.")
    else:
        p = problem
        st.markdown(f"**Size:** {p.m} sources × {p.n} destinations = **{p.m * p.n} decision variables**, "
                    f"**{p.m + p.n} constraints** (plus nonnegativity).")
        st.markdown("#### Decision variables")
        st.latex(r"x_{ij} = \text{units shipped from warehouse } i \text{ to store } j")
        st.markdown("#### General form")
        st.latex(tp.latex_general(p))
        if p.supply_sense == "<=":
            st.caption("Supply rows use ≤ because a warehouse doesn't have to ship everything it has. "
                       "Demand rows use = because every store must get exactly what it needs.")
        else:
            st.caption("Balanced form: with the dummy node, total supply equals total demand, so both sets of "
                       "constraints are equalities.")
        a, b = st.columns(2)
        with a:
            st.markdown("**Index i: sources**")
            st.dataframe(pd.DataFrame({"i": range(1, p.m + 1), "Warehouse": p.sources, "Supply sᵢ": p.supply}),
                         hide_index=True, width="stretch")
        with b:
            st.markdown("**Index j: destinations**")
            st.dataframe(pd.DataFrame({"j": range(1, p.n + 1), "Store": p.dests, "Demand dⱼ": p.demand}),
                         hide_index=True, width="stretch")
        st.markdown("**Cost coefficients cᵢⱼ ($/unit)**")
        st.dataframe(pd.DataFrame(p.cost, index=[f"{i + 1}: {n}" for i, n in enumerate(p.sources)],
                                  columns=[f"{j + 1}: {n}" for j, n in enumerate(p.dests)]),
                     width="stretch")
        with st.expander("Fully expanded model with your numbers", expanded=p.m * p.n <= 40):
            expanded = tp.latex_expanded(p)
            st.latex(expanded)
        with st.expander("LaTeX source (copy into a report)"):
            st.code("% General form\n" + tp.latex_general(p).strip() + "\n\n% Expanded form\n" + expanded,
                    language="latex")

# ---- Solution ---- #
with t_sol:
    if not problem:
        st.info("Add at least one warehouse and one store.")
    elif not sol.optimal:
        st.warning("There's no optimal solution to show. See the message above the map.")
    else:
        p = problem
        ship_rows = [{"From": p.sources[i], "To": p.dests[j], "Units": sol.x[i][j],
                      "Cost/unit": p.cost[i][j], "Route cost": sol.x[i][j] * p.cost[i][j]}
                     for i in range(p.m) for j in range(p.n) if sol.x[i][j] > 0]
        ship_df = pd.DataFrame(ship_rows)
        money = st.column_config.NumberColumn(format="$%.2f")
        st.markdown(f"#### Optimal shipping plan · Z = {tp.fmt(sol.objective, True)}")
        st.dataframe(ship_df, hide_index=True, width="stretch",
                     column_config={"Cost/unit": money, "Route cost": money})
        st.download_button("⬇️ Download plan (.csv)", ship_df.to_csv(index=False), "shipping_plan.csv", "text/csv")

        a, b = st.columns(2)
        with a:
            st.markdown("#### Warehouses")
            st.dataframe(pd.DataFrame([{
                "Warehouse": p.sources[i], "Supply": p.supply[i], "Shipped": sum(sol.x[i]),
                "Unused": p.supply[i] - sum(sol.x[i]),
                "% used": 100 * sum(sol.x[i]) / p.supply[i] if p.supply[i] else 0.0,
                "Shadow price": sol.supply_duals[i],
            } for i in range(p.m)]), hide_index=True, width="stretch",
                column_config={"% used": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100),
                               "Shadow price": money})
        with b:
            st.markdown("#### Stores")
            st.dataframe(pd.DataFrame([{
                "Store": p.dests[j], "Demand": p.demand[j],
                "Received": sum(sol.x[i][j] for i in range(p.real_m)),
                "Shadow price": sol.demand_duals[j],
            } for j in range(p.n)]), hide_index=True, width="stretch",
                column_config={"Shadow price": money})
        with st.expander("What do the shadow prices and reduced costs mean?"):
            st.markdown(
                "- **Warehouse shadow price** (dual of the supply constraint): how much the total cost changes if "
                "that warehouse had **one more unit** of supply. A negative value means extra capacity there "
                "would save money. Zero means the warehouse already has spare capacity.\n"
                "- **Store shadow price** (dual of the demand constraint): how much the total cost rises if that "
                "store needed **one more unit**.\n"
                "- **Reduced cost** of an unused route: how much its cost per unit would have to drop before "
                "using it could lower the total cost.\n\n"
                "These hold for small changes. When the solution is degenerate, the duals may not be unique.")
            rc = pd.DataFrame([{"Route": f"{p.sources[i]} → {p.dests[j]}", "Cost/unit": p.cost[i][j],
                                "Reduced cost": sol.reduced_costs[i][j]}
                               for i in range(p.m) for j in range(p.n) if sol.x[i][j] == 0])
            if not rc.empty:
                st.markdown("**Unused routes**")
                st.dataframe(rc.sort_values("Reduced cost"), hide_index=True, width="stretch",
                             column_config={"Cost/unit": money, "Reduced cost": money})

# ---- Verify ---- #
with t_ver:
    if not problem:
        st.info("Add at least one warehouse and one store.")
    else:
        p = problem
        st.markdown("Don't take the app's word for it. Export this exact model and solve it with another tool. "
                    "The **minimum cost should match**. The shipments themselves can differ when a problem "
                    "has more than one optimal plan.")
        if sol.optimal:
            st.success(f"App's answer to compare against: **Z = {tp.fmt(sol.objective, True)}**")

        st.markdown("### 1. Excel Solver (recommended)")
        st.markdown("A workbook with the costs, supplies and demands, plus a **Solver model already set up**. "
                    "Open it, go to **Data → Solver → Solve**, and compare the total cost with the app's. The "
                    "Instructions sheet covers turning on Solver and entering the model by hand in Excel on "
                    "the web or LibreOffice.")
        st.download_button("⬇️ Download Excel workbook (.xlsx)", exports.excel_workbook(p, sol),
                           "transportation_model.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        st.markdown("### 2. Online simplex tool (copy and paste)")
        text, seq = exports.simplex_tool_text(p)
        st.markdown(f"Copy the text below (copy button at its top right) and paste it into the "
                    f"[Finite Mathematics simplex method tool]({exports.SIMPLEX_URL}), then click **Solve**. "
                    f"It only accepts ≤ and ≥, so demand rows are written as ≥. With nonnegative costs the "
                    f"optimal cost is the same.")
        if seq:
            st.caption("Variables are numbered row by row: x1 … x{n} are shipments from the first warehouse to "
                       "each store, and so on.".format(n=p.n))
        st.code(text, language=None)

        st.markdown("### 3. NEOS Server (industrial solvers, any size)")
        st.markdown(f"Download the model in standard **CPLEX LP format** and upload it to the free "
                    f"[NEOS Server HiGHS page]({exports.NEOS_URL}). Results appear in the browser, and NEOS may "
                    f"ask for an email address. The same file also works with GLPK, CPLEX and Gurobi.")
        lp_text = tp.lp_file_text(p)
        st.download_button("⬇️ Download model (.lp)", lp_text, "transportation_model.lp", "text/plain")
        with st.expander("Preview the .lp file"):
            st.code(lp_text, language=None)

        st.markdown("### 4. Wolfram|Alpha (tiny problems only)")
        wa = exports.wolfram_url(p)
        if wa:
            url, legend = wa
            st.link_button("Open this problem in Wolfram|Alpha ↗", url)
            st.caption("Variable key: " + ", ".join(f"**{v}** = {a} → {b}" for v, (a, b) in legend.items()))
        else:
            st.caption(f"Available when the model has at most {exports.WOLFRAM_MAX_VARS} variables (for example "
                       f"2 warehouses × 3 stores). This one has {p.m * p.n}, which is too long for "
                       f"Wolfram|Alpha's input box.")

# ---- Compare ---- #
with t_cmp:
    base = st.session_state.baseline
    st.markdown("Save the current plan as a **baseline**, change the scenario (close a warehouse, raise a "
                "demand, edit a cost), and compare the two plans here.")
    a, b = st.columns(2)
    a.button("📌 Save current plan as baseline", on_click=cb_save_baseline, args=(problem, sol),
             disabled=not (sol and sol.optimal), width="stretch")
    if base:
        b.button("Clear baseline", on_click=lambda: st.session_state.update(baseline=None), width="stretch")

    if not base:
        st.info("No baseline saved yet.")
    elif not (sol and sol.optimal):
        st.warning("The current scenario has no optimal solution, so there's nothing to compare.")
    else:
        bp, bs = base["problem"], base["sol"]

        def plan(p_, s_):
            return {(p_.sources[i], p_.dests[j]): s_.x[i][j]
                    for i in range(p_.m) for j in range(p_.n) if s_.x[i][j] > 0}

        def stats(p_, s_):
            pl = plan(p_, s_)
            real = {k: v for k, v in pl.items() if tp.DUMMY_SOURCE not in k and tp.DUMMY_DEST not in k}
            return s_.objective, sum(real.values()), len(real)

        (bc, bu, br), (cc, cu, cr) = stats(bp, bs), stats(problem, sol)
        st.caption(base["label"])
        m1, m2, m3 = st.columns(3)
        m1.metric("Total cost", tp.fmt(cc, True), delta=tp.fmt(cc - bc, True) if cc != bc else None,
                  delta_color="inverse")
        m2.metric("Units shipped", tp.fmt(cu), delta=tp.fmt(cu - bu) if cu != bu else None)
        m3.metric("Routes used", cr, delta=cr - br if cr != br else None, delta_color="off")
        bpl, cpl = plan(bp, bs), plan(problem, sol)
        rows = [{"From": k[0], "To": k[1], "Baseline": bpl.get(k, 0.0), "Current": cpl.get(k, 0.0),
                 "Change": cpl.get(k, 0.0) - bpl.get(k, 0.0)} for k in sorted(set(bpl) | set(cpl))]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
