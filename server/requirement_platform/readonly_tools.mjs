// Trusted, application-owned DSH plugin. No generic filesystem, shell or URL tools.
export const name = 'trailsnap-readonly-knowledge'
export const inject = ['tools']

export function apply(ctx, config) {
  const definitions = [
    ['search_trailsnap_code', 'Search the fixed latest TrailSnap release source. Use short code identifiers or keywords.',
      { query: { type: 'string', maxLength: 120 } }, ['query']],
    ['read_trailsnap_source', 'Read up to 50 lines from an exact source path returned by code search.',
      { path: { type: 'string', maxLength: 500 }, start_line: { type: 'integer', minimum: 1 } }, ['path']],
    ['search_official_docs', 'Search cached official TrailSnap website documentation. Use short product keywords.',
      { query: { type: 'string', maxLength: 120 } }, ['query']],
  ]
  for (const [name, description, properties, required] of definitions) {
    ctx.tools.register({
      name, description,
      parameters: { type: 'object', properties, required, additionalProperties: false },
      output: { schema: { type: 'object' }, render(_args, value) { return [{ type: 'text', text: JSON.stringify(value) }] } },
      async execute(args) {
        const response = await fetch(config.endpoint + '/' + name, {
          method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + config.token },
          body: JSON.stringify(args), signal: AbortSignal.timeout(5000),
        })
        if (!response.ok) throw new Error('Readonly retrieval unavailable or limit reached')
        return response.json()
      },
    })
  }
}
