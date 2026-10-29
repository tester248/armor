// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ['dist/*'],
    rules: {
      // The operator console polls the gateway: each screen kicks off a fetch on
      // mount and every N seconds after that. The rule flags the mount-time call
      // because it lands a setState in the same tick, but that is the intended
      // "show cached state immediately, then refresh" behaviour here. Effects are
      // still cleaned up, so this is a warning rather than an error.
      'react-hooks/set-state-in-effect': 'warn',
    },
  },
]);
