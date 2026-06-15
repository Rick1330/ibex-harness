import { PostCard } from "@/components/blog/post-card";

type PostGridItem = {
  url: string;
  data: {
    title: string;
    date: string;
    excerpt?: string;
    tags?: string[];
    readingTime?: string;
    author?: string;
    authorUrl?: string;
  };
};

type PostGridProps = Readonly<{
  posts: PostGridItem[];
}>;

export function PostGrid({ posts }: PostGridProps) {
  if (posts.length === 0) {
    return (
      <div className="rounded-xl border border-border bg-card px-6 py-16 text-center">
        <p className="text-sm text-muted-foreground">No posts match this filter.</p>
      </div>
    );
  }

  return (
    <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
      {posts.map((post) => (
        <PostCard
          key={post.url}
          url={post.url}
          title={post.data.title}
          date={post.data.date}
          excerpt={post.data.excerpt}
          tags={post.data.tags}
          readingTime={post.data.readingTime}
          author={post.data.author}
          authorUrl={post.data.authorUrl}
        />
      ))}
    </div>
  );
}
