"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";

export function RouteProgress() {
  const pathname = usePathname();
  const [visible, setVisible] = useState(false);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    setVisible(true);
    setWidth(25);
    const t1 = window.setTimeout(() => setWidth(70), 120);
    const t2 = window.setTimeout(() => setWidth(95), 350);
    const t3 = window.setTimeout(() => {
      setWidth(100);
      window.setTimeout(() => {
        setVisible(false);
        setWidth(0);
      }, 180);
    }, 550);
    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
      window.clearTimeout(t3);
    };
  }, [pathname]);

  if (!visible) return null;
  return (
    <div className="fixed top-0 left-0 right-0 z-[100] h-1 bg-transparent">
      <div
        className="h-full bg-[hsl(var(--primary))] transition-all duration-200"
        style={{ width: `${width}%` }}
      />
    </div>
  );
}
