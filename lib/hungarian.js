'use strict';

/**
 * Rectangular Hungarian (Kuhn-Munkres) assignment algorithm.
 * Solves minimum weight bipartite matching for matrix of size m x n with m <= n.
 * Runs in O(m^2 * n) time.
 * @param {number[][]} matrix Rectangular cost matrix (m rows <= n cols)
 * @returns {Int32Array} Array of length m where rowMatches[i] is the matched column j
 */
function hungarian(matrix) {
  const m = matrix.length;
  if (m === 0) return new Int32Array(0);
  const n = matrix[0].length;
  if (n === 0) return new Int32Array(0);
  if (m > n) {
    throw new Error(`Hungarian: rows m (${m}) must be <= cols n (${n})`);
  }

  // 1-based indexing for standard potential reduction formulation
  const u = new Float64Array(m + 1);
  const v = new Float64Array(n + 1);
  const p = new Int32Array(n + 1);
  const way = new Int32Array(n + 1);

  for (let i = 1; i <= m; i++) {
    p[0] = i;
    let j0 = 0;
    const minv = new Float64Array(n + 1).fill(Infinity);
    const used = new Uint8Array(n + 1);

    do {
      used[j0] = 1;
      const i0 = p[j0];
      let delta = Infinity;
      let j1 = 0;

      for (let j = 1; j <= n; j++) {
        if (!used[j]) {
          const cur = matrix[i0 - 1][j - 1] - u[i0] - v[j];
          if (cur < minv[j]) {
            minv[j] = cur;
            way[j] = j0;
          }
          if (minv[j] < delta) {
            delta = minv[j];
            j1 = j;
          }
        }
      }

      for (let j = 0; j <= n; j++) {
        if (used[j]) {
          u[p[j]] += delta;
          v[j] -= delta;
        } else {
          minv[j] -= delta;
        }
      }

      j0 = j1;
    } while (p[j0] !== 0);

    do {
      const j1 = way[j0];
      p[j0] = p[j1];
      j0 = j1;
    } while (j0 !== 0);
  }

  const rowMatches = new Int32Array(m);
  for (let j = 1; j <= n; j++) {
    if (p[j] > 0 && p[j] <= m) {
      rowMatches[p[j] - 1] = j - 1;
    }
  }
  return rowMatches;
}

/**
 * Solve assignment problem for m x n cost matrix.
 * If row minima are independent (no column collisions), uses greedy assignment
 * which achieves the lower bound and is optimal.
 * Otherwise uses rectangular Hungarian algorithm.
 * Handles both m <= n and m > n orientations.
 * @param {number[][]} costMatrix
 * @returns {Array<[number, number]>} List of [row, col] pairs assigned
 */
function solveAssignment(costMatrix) {
  const m = costMatrix.length;
  if (m === 0) return [];
  const n = costMatrix[0].length;
  if (n === 0) return [];

  let swap = false;
  let C = costMatrix;
  let rows = m;
  let cols = n;

  if (rows > cols) {
    swap = true;
    C = new Array(cols);
    for (let j = 0; j < cols; j++) {
      C[j] = new Array(rows);
      for (let i = 0; i < rows; i++) {
        C[j][i] = costMatrix[i][j];
      }
    }
    rows = cols;
    cols = m;
  }

  // Try greedy assignment first: each row picks column with minimum cost
  const greedyCols = new Int32Array(rows);
  const usedCols = new Set();
  let greedyValid = true;

  for (let i = 0; i < rows; i++) {
    let minVal = Infinity;
    let minCol = -1;
    for (let j = 0; j < cols; j++) {
      if (C[i][j] < minVal) {
        minVal = C[i][j];
        minCol = j;
      }
    }
    greedyCols[i] = minCol;
    if (usedCols.has(minCol)) {
      greedyValid = false;
    }
    usedCols.add(minCol);
  }

  const assigned = greedyValid ? greedyCols : hungarian(C);

  const result = [];
  if (!swap) {
    for (let i = 0; i < rows; i++) {
      result.push([i, assigned[i]]);
    }
  } else {
    for (let j = 0; j < rows; j++) {
      result.push([assigned[j], j]);
    }
  }
  return result;
}

module.exports = {
  hungarian,
  solveAssignment
};
