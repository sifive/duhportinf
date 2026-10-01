'use strict';

/**
 * Split name into words according to DUH legacy naming rules.
 * @param {string} name
 * @returns {string[]}
 */
function wordsFromName(name) {
  // convert camelcase to '_'
  name = name.replace(/(.)([A-Z][a-z]+)(.)/g, '$1_$2$3');
  // always return lower case so case insensitive
  name = name.replace(/([a-z0-9])([A-Z])/g, '$1_$2').toLowerCase();
  // insert '_' in between names and numbers
  name = name.replace(/([a-zA-Z])([0-9]+)/g, '$1_$2').toLowerCase();
  return name.split('_');
}

/**
 * All 1-, 2-, and 3-character tokens within a single string with '_' stripped.
 * @param {string} n
 * @returns {string[]}
 */
function getTokensSingle(n) {
  if (typeof n !== 'string') {
    n = String(n || '');
  }
  const clean = n.replace(/_/g, '').toLowerCase();
  const tokens = [];
  const len = clean.length;
  for (let i = 0; i < len; i++) {
    tokens.push(clean[i]);
  }
  for (let i = 0; i < len - 1; i++) {
    tokens.push(clean.slice(i, i + 2));
  }
  for (let i = 0; i < len - 2; i++) {
    tokens.push(clean.slice(i, i + 3));
  }
  return tokens;
}

/**
 * All tokens within a string or iterable of strings.
 * @param {string|Iterable<string>} n
 * @returns {string[]}
 */
function getTokens(n) {
  if (Array.isArray(n) || n instanceof Set) {
    const tokens = [];
    for (const item of n) {
      tokens.push(...getTokensSingle(item));
    }
    return tokens;
  }
  return getTokensSingle(n);
}

/**
 * Jaccard distance of tokens within n1 and n2.
 * @param {string|Iterable<string>} n1
 * @param {string|Iterable<string>} n2
 * @returns {number}
 */
function getJaccardDist(n1, n2) {
  const n1t = new Set(getTokens(n1));
  const n2t = new Set(getTokens(n2));
  if (n1t.size === 0 && n2t.size === 0) {
    return 0;
  }
  let intersectionSize = 0;
  for (const t of n1t) {
    if (n2t.has(t)) {
      intersectionSize++;
    }
  }
  const unionSize = n1t.size + n2t.size - intersectionSize;
  if (unionSize === 0) {
    return 0;
  }
  const jaccardIndex = intersectionSize / unionSize;
  return 1 - jaccardIndex;
}

/**
 * Number of tokens in n1 that are not present in n2.
 * @param {string|Iterable<string>} n1
 * @param {string|Iterable<string>} n2
 * @returns {number}
 */
function getNumMissingTokens(n1, n2) {
  const n1t = new Set(getTokens(n1));
  const n2t = new Set(getTokens(n2));
  let count = 0;
  for (const t of n1t) {
    if (!n2t.has(t)) {
      count++;
    }
  }
  return count;
}

/**
 * Fraction of tokens in n1 that are not present in n2.
 * @param {string|Iterable<string>} n1
 * @param {string|Iterable<string>} n2
 * @returns {number}
 */
function getFracMissingTokens(n1, n2) {
  const n1t = new Set(getTokens(n1));
  if (n1t.size === 0) {
    return 0;
  }
  const n2t = new Set(getTokens(n2));
  let count = 0;
  for (const t of n1t) {
    if (!n2t.has(t)) {
      count++;
    }
  }
  return count / n1t.size;
}

/**
 * Longest common leading substring among an array of strings.
 * @param {string[]} words
 * @returns {string}
 */
function commonPrefix(words) {
  if (!words || words.length === 0) {
    return '';
  }
  let n1 = words[0];
  let n2 = words[0];
  for (let i = 1; i < words.length; i++) {
    if (words[i] < n1) n1 = words[i];
    if (words[i] > n2) n2 = words[i];
  }
  for (let i = 0; i < n1.length; i++) {
    if (n1[i] !== n2[i]) {
      return n1.slice(0, i);
    }
  }
  return n1;
}

/**
 * Check if integer array represents a contiguous range [min..max].
 * @param {number[]} digits
 * @returns {boolean}
 */
function isRange(digits) {
  if (!Array.isArray(digits) || digits.length === 0) {
    return false;
  }
  let min = digits[0];
  let max = digits[0];
  const set = new Set();
  for (let i = 0; i < digits.length; i++) {
    const d = digits[i];
    if (typeof d !== 'number' || !Number.isInteger(d)) {
      return false;
    }
    if (set.has(d)) {
      return false; // duplicates not a range
    }
    set.add(d);
    if (d < min) min = d;
    if (d > max) max = d;
  }
  return (max - min + 1) === digits.length;
}

module.exports = {
  wordsFromName,
  getTokensSingle,
  getTokens,
  getJaccardDist,
  getNumMissingTokens,
  getFracMissingTokens,
  commonPrefix,
  isRange
};
