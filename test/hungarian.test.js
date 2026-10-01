'use strict';

const { expect } = require('chai');
const { hungarian, solveAssignment } = require('../lib/hungarian');

function bruteForce(matrix) {
  const m = matrix.length;
  const n = matrix[0].length;
  let minCost = Infinity;
  let bestAssignment = null;

  function backtrack(row, usedCols, cost, current) {
    if (row === m) {
      if (cost < minCost) {
        minCost = cost;
        bestAssignment = [...current];
      }
      return;
    }
    for (let c = 0; c < n; c++) {
      if (!usedCols.has(c)) {
        usedCols.add(c);
        current.push([row, c]);
        backtrack(row + 1, usedCols, cost + matrix[row][c], current);
        current.pop();
        usedCols.delete(c);
      }
    }
  }

  backtrack(0, new Set(), 0, []);
  return { minCost, bestAssignment };
}

describe('Hungarian Assignment Solver', () => {
  it('handles empty matrices', () => {
    expect(hungarian([])).to.have.lengthOf(0);
    expect(solveAssignment([])).to.have.lengthOf(0);
    expect(solveAssignment([[]])).to.have.lengthOf(0);
  });

  it('handles 1x1 matrix', () => {
    const res = solveAssignment([[42]]);
    expect(res).to.deep.equal([[0, 0]]);
  });

  it('handles rectangular matrices (m < n)', () => {
    const mat = [
      [10, 5, 20],
      [2, 50, 8]
    ];
    const res = solveAssignment(mat);
    expect(res).to.deep.equal([[0, 1], [1, 0]]);
  });

  it('handles rectangular matrices (m > n)', () => {
    const mat = [
      [10, 2],
      [5, 50],
      [20, 8]
    ];
    const res = solveAssignment(mat);
    // col 0 best with row 1 (cost 5), col 1 best with row 0 (cost 2)
    const cost = res.reduce((acc, [r, c]) => acc + mat[r][c], 0);
    expect(cost).to.equal(7);
  });

  it('agrees with brute-force on 50 random rectangular matrices', () => {
    for (let trial = 0; trial < 50; trial++) {
      const m = 1 + Math.floor(Math.random() * 5);
      const n = m + Math.floor(Math.random() * 4);
      const mat = [];
      for (let i = 0; i < m; i++) {
        mat.push([]);
        for (let j = 0; j < n; j++) {
          mat[i].push(Math.round(Math.random() * 200 - 50) / 10);
        }
      }

      const res = solveAssignment(mat);
      let hCost = 0;
      const assignedCols = new Set();
      for (const [r, c] of res) {
        hCost += mat[r][c];
        assignedCols.add(c);
      }
      expect(assignedCols.size).to.equal(m);

      const bf = bruteForce(mat);
      expect(Math.abs(hCost - bf.minCost)).to.be.lessThan(1e-6);
    }
  });

  it('handles matrices with identical costs (ties)', () => {
    const mat = [
      [1, 1, 1],
      [1, 1, 1]
    ];
    const res = solveAssignment(mat);
    expect(res).to.have.lengthOf(2);
    const cols = new Set(res.map(([, c]) => c));
    expect(cols.size).to.equal(2);
  });
});
