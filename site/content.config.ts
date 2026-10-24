import { defineCollection, defineContentConfig, z } from '@nuxt/content'

const shared = z.object({
  status: z.enum(['IMPLEMENTED', 'PROVISIONAL', 'PROPOSED', 'DEFERRED', 'UNKNOWN']).optional(),
  scope: z.string().optional(),
  verifiedDate: z.string().optional(),
  sourceOfTruth: z.string().optional(),
  audience: z.string().optional(),
  readingTime: z.string().optional(),
  excerpt: z.string().optional(),
  author: z.string().optional(),
  authorUrl: z.string().optional(),
  featured: z.boolean().optional(),
  tags: z.array(z.string()).optional(),
  decisionStatus: z.string().optional(),
  date: z.string().optional(),
  historical: z.boolean().optional(),
  coverIndex: z.number().int().min(1).optional(),
  coverTone: z.number().int().min(1).max(3).optional(),
  coverLabel: z.string().max(40).optional(),
}).passthrough()

export default defineContentConfig({
  collections: {
    docs: defineCollection({
      type: 'page',
      source: {
        cwd: 'content',
        include: 'docs/**',
        prefix: '/docs',
      },
      schema: shared,
    }),
    blog: defineCollection({
      type: 'page',
      source: {
        cwd: 'content',
        include: 'blog/**',
        prefix: '/blog',
      },
      schema: shared,
    }),
  },
})
