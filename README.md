# Interactive Delivery and Distribution Optimizer

A map-based web app that solves the **transportation problem** with linear programming: find how many units to
ship from each warehouse to each store so that every store's demand is met, no warehouse ships more than it has,
and total shipping cost is as low as possible.

**Live app:** _add your Streamlit Cloud link here_

## What it does

- **Build a scenario on a U.S. map.** Click the map to place warehouses and stores, or pick from a city list.
  Edit names, supplies and demands in tables.
- **Shipping costs.** Each route starts at a distance-based estimate ($/unit/mile × straight-line miles). You can
  override any route.
- **The LP model, written out.** The app generates the formulation in LaTeX: decision variables, objective,
  supply constraints, demand constraints and nonnegativity, in both summation and fully expanded form.
- **Solve and visualize.** Optimal routes are drawn on the map, with line width and labels showing quantities. The
  app also shows a shipment table, total cost, warehouse use, shadow prices and reduced costs.
- **Unbalanced problems.** If demand exceeds supply, the app explains why the model is infeasible. A switch turns
  on the textbook fix (a dummy warehouse or store).
- **Compare scenarios.** Save a baseline, change something, and see how the cost and the routes change.
- **Verify externally.** Export the same model to Excel Solver (preconfigured workbook), an online simplex tool
  (copy and paste), the NEOS Server (CPLEX `.lp` file) or Wolfram|Alpha (tiny problems).

The **"Textbook check: P&T Company"** example reproduces the problem from Hillier & Lieberman's *Introduction to
Operations Research*. The app's optimal cost, $152,535, matches the book.

## Mathematical model

$$
\begin{aligned}
\min\; Z = & \sum_{i=1}^{m} \sum_{j=1}^{n} c_{ij} x_{ij} \\
\text{s.t.}\quad & \sum_{j=1}^{n} x_{ij} \le s_i, && i = 1,\dots,m \quad \text{(supply)}\\
& \sum_{i=1}^{m} x_{ij} = d_j, && j = 1,\dots,n \quad \text{(demand)}\\
& x_{ij} \ge 0
\end{aligned}
$$

## Project files

| File | Purpose |
|---|---|
| `app.py` | Streamlit user interface: map, tables, tabs |
| `transport.py` | Builds the LP from a scenario, solves it with PuLP + HiGHS, generates the LaTeX |
| `exports.py` | Excel Solver workbook, online-solver text, Wolfram|Alpha link |
| `scenarios.py` | Built-in example scenarios and save/load as JSON |
| `cities.py` | U.S. city coordinates and distance calculation |

## Run it locally

Requires Python 3.10+.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
streamlit run app.py
```

## Deploy to Streamlit Community Cloud (free)

1. Push this folder to a public GitHub repository.
2. Sign in at <https://share.streamlit.io> with GitHub and click **Create app**.
3. Pick the repository, branch `main`, main file `app.py`. Under **Advanced settings**, choose Python 3.13.
4. Click **Deploy**. After a few minutes you get a public `https://<name>.streamlit.app` link.

Free apps go to sleep after a period with no visitors. If you see a "wake up" button, click it and wait about
30 seconds.
