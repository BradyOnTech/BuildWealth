// Milestones — derive the years a person anchors on from a deterministic
// scenario timeline: when drawdown begins, when compounding outpaces saving,
// and the earliest year contributions could stop without sinking the plan.
//
// These are estimates replayed from the engine's own timeline (same balances,
// withdrawals, and implied returns), not fresh simulations: taxes are held as
// projected, so treat results as directional. The engine remains canonical if
// these ever feed recommendations.

export function firstDrawdownYear(points = []) {
  for (const point of normalize(points)) {
    if (point.withdrawals > 0) return point.year;
  }
  return null;
}

// First pre-drawdown year where market growth exceeds contributions and keeps
// exceeding them for the rest of the accumulation phase (a single lucky year
// is not a crossover).
export function crossoverYear(points = []) {
  const rows = normalize(points).filter(point => point.contributions > 0 && point.withdrawals <= 0);
  if (!rows.length) return null;
  for (let index = 0; index < rows.length; index++) {
    if (rows[index].growth <= rows[index].contributions) continue;
    const sustained = rows.slice(index).every(row => row.growth > row.contributions);
    if (sustained) return rows[index].year;
  }
  return null;
}

// Earliest year Y such that replaying the timeline from Y with zero further
// contributions — same withdrawals, same implied yearly returns — keeps the
// balance above zero through the final projected year.
export function coastFireYear(points = []) {
  const rows = normalize(points);
  if (rows.length < 2) return null;
  const firstWithdrawal = rows.findIndex(row => row.withdrawals > 0);
  if (firstWithdrawal < 0) return null;
  // A plan that already fails on its own timeline has no coast year.
  if (rows.some(row => row.ending <= 0 && row.withdrawals > 0)) return null;

  for (let start = 0; start < firstWithdrawal; start++) {
    if (rows[start].contributions <= 0 && start > 0) continue; // coasting is only meaningful while still contributing
    if (survivesWithoutContributions(rows, start)) return rows[start].year;
  }
  return null;
}

export function milestoneAges(points = [], years = []) {
  const byYear = new Map(normalize(points).map(point => [point.year, point.age]));
  return years.map(year => (year != null && byYear.has(year) ? byYear.get(year) : null));
}

function survivesWithoutContributions(rows, start) {
  let balance = rows[start].ending;
  for (let index = start + 1; index < rows.length; index++) {
    const row = rows[index];
    balance -= row.withdrawals;
    if (balance <= 0) return false;
    balance *= 1 + impliedReturn(row);
    if (balance <= 0) return false;
  }
  return balance > 0;
}

// The engine applies flows first, then growth; recover the rate it used.
function impliedReturn(row) {
  const base = row.starting + row.contributions - row.withdrawals;
  if (base <= 0) return 0;
  return row.growth / base;
}

function normalize(points) {
  return (Array.isArray(points) ? points : [])
    .filter(point => point && typeof point === 'object')
    .map(point => ({
      year: toNumber(point.year),
      age: toNumber(point.age),
      starting: toNumber(point.starting_balance_usd),
      ending: toNumber(point.ending_balance_usd),
      contributions: toNumber(point.contributions_usd),
      withdrawals: toNumber(point.withdrawals_usd),
      growth: toNumber(point.growth_usd),
    }))
    .filter(point => Number.isFinite(point.year));
}

function toNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}
