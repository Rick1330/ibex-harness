import { queryCollection } from '@nuxt/content/nitro'

export default defineSitemapEventHandler(async (event) => {
  const posts = await queryCollection(event, 'blog')
    .select('path', 'date')
    .all()

  return posts
    .filter(post => post.path.startsWith('/blog/'))
    .map(post => ({
      loc: post.path,
      lastmod: post.date,
    }))
})
