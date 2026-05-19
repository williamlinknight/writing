import rss from '@astrojs/rss';
import { getCollection } from 'astro:content';

export async function GET(context) {
  const posts = await getCollection('blog');
  
  return rss({
    title: '厦门灯塔 | 英文作文批改博客',
    description: '专业英文作文逐句批改服务 · 中高考/雅思写作提分指南 · 厦门灯塔威廉老师',
    site: context.site,
    items: posts.map((post) => ({
      title: post.data.title,
      pubDate: post.data.pubDate,
      description: post.data.description,
      link: `/blog/${post.id.replace(/\.(md|mdx)$/, '')}`,
    })),
    customData: '<language>zh-CN</language>',
    trailingSlash: false,
  });
}
