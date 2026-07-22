import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="container page">
      <h1>Page not found</h1>
      <p className="lede">
        We couldn&rsquo;t find what you were looking for. It may have moved or the
        training may no longer be open.
      </p>
      <Link className="btn btn-primary" href="/trainings">
        Browse trainings
      </Link>
    </div>
  );
}
