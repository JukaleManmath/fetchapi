import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4 py-24 text-center px-6">
      <p className="font-mono text-4xl font-bold text-text-muted">404</p>
      <p className="text-sm text-text-secondary">Page not found</p>
      <Link href="/">
        <Button variant="secondary" size="sm">
          Back to sources
        </Button>
      </Link>
    </div>
  );
}
