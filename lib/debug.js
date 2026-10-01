'use strict';

/**
 * Format structured versioned debug report for CLI --debug flag.
 * @param {object} options
 * @returns {object}
 */
function createDebugReport(options = {}) {
  const {
    formatVersion = '1.0.0',
    metadata = {},
    portGroups = [],
    selectedInterfaces = [],
    alternateInterfaces = [],
    busDefinitions = {},
    diagnostics = []
  } = options;

  return {
    formatVersion,
    metadata: {
      tool: 'duh-portinf',
      version: '0.5.0',
      timestamp: new Date().toISOString(),
      ...metadata
    },
    portGroups,
    selectedInterfaces,
    alternateInterfaces,
    busDefinitions,
    diagnostics
  };
}

module.exports = {
  createDebugReport
};
