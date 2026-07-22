import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function formatRelativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function httpMethodColor(method: string): string {
  const m = method.toUpperCase();
  const map: Record<string, string> = {
    GET: "text-emerald-700",
    POST: "text-blue-700",
    PUT: "text-amber-700",
    PATCH: "text-orange-700",
    DELETE: "text-red-700",
    HEAD: "text-purple-700",
    OPTIONS: "text-zinc-500",
  };
  return map[m] ?? "text-zinc-500";
}
