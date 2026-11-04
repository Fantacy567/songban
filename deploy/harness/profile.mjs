// Copyright (c) 2026 2292576833. Upstream retains its MIT license.
// Shared pure profile construction: no server, process launch or file writes.
export function studioPatch(input, port) {
  const disabled = ['llm-deepseek', 'persistent-bash', 'persistent-pwsh', 'terminal-bash',
    'terminal-pwsh', 'tool-working-directory', 'compaction-basic', 'image-offload'];
  return [
    ...disabled.map(id => ({ id, disabled: true })),
    { id: 'tool-fs', config: { read: true, readImage: false, write: true, edit: true, applyPatch: false } },
    { id: 'sdk-jsonrpc-server', inject: ['sdkAppStartup', 'loader', 'songbanFileGuard'], config: { maxTokensAsSuccess: false } },
    { id: 'system-prompt', config: { includeHarnessIdentity: false, includeRuntimeContext: false, personaPrefix: input.input.teaching } },
    { insert: [
      { id: 'songban-file-guard', name: '/opt/harness/file-guard.mjs' },
      { id: 'songban-model', name: '@deepseek-ai/dsh-llm-pi-ai', config: { providers: { 'songban-server': {
        apiKeyEnv: 'SONGBAN_RELAY_TOKEN', api: 'openai-completions', baseURL: `http://127.0.0.1:${port}/v1`,
        defaultContextWindow: 64000, defaultMaxTokens: input.max_tokens,
        retryPolicy: { mode: 'normal', maxRetries: 0 },
        models: [{ id: input.model, name: input.model, contextWindow: 64000, reasoningEfforts: false }],
        compat: { thinkingFormat: 'deepseek' },
      } } } },
    ] },
  ];
}

export function studioOptions(input, env) {
  return { profile: 'sdk-minimal', dshHome: '/tmp/dsh', processCwd: '/work', cwd: '/work',
    patches: ['/tmp/songban.patch.yml'], provider: 'songban-server', model: input.model, maxTokens: input.max_tokens,
    env: { PATH: env.PATH, HOME: '/tmp', DSH_HOME: '/tmp/dsh', SONGBAN_RELAY_TOKEN: 'local-stdio-relay-not-a-secret' },
    onUserQuestion: async () => ({ cancelled: true }), initializeTimeoutMs: 30000, requestTimeoutMs: 180000 };
}
