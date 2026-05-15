import { defineCollection, z } from 'astro:content';

const blog = defineCollection({
  // Type-check frontmatter
  schema: z.object({
    title: z.string(),
    pubDate: z.date(),
    description: z.string(),
    author: z.string().optional(),
  }),
});

export const collections = {
  blog,
};