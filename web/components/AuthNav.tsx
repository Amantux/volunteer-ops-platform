'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { clearToken, getToken } from '@/lib/auth';

// Auth state lives in localStorage (client-only), so this nav renders nothing
// auth-specific until mounted to avoid a hydration mismatch with the server.
export default function AuthNav() {
  const router = useRouter();
  const pathname = usePathname();
  const [signedIn, setSignedIn] = useState<boolean | null>(null);

  useEffect(() => {
    setSignedIn(!!getToken());
  }, [pathname]);

  function signOut() {
    clearToken();
    setSignedIn(false);
    router.replace('/');
  }

  // Pre-hydration: don't guess — keep the slot empty to match SSR output.
  if (signedIn === null) return null;

  if (signedIn) {
    return (
      <>
        <Link href="/dashboard">Dashboard</Link>
        <button type="button" className="nav-signout" onClick={signOut}>
          Sign out
        </button>
      </>
    );
  }

  return <Link href="/login">Sign in</Link>;
}
