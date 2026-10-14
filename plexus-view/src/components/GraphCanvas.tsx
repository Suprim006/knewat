import { useEffect, useRef } from 'react';
import { createGraphController, DARK_THEME, LIGHT_THEME } from '../lib/graphController';
import type { GraphController } from '../lib/graphController';
import { useIsDark } from '../lib/theme';

interface Props {
  /** Called with the controller once mounted, and with null on unmount. Must be a stable function. */
  onReady: (c: GraphController | null) => void;
  onSelect: (id: string | null) => void;
}

const isJsdom = (): boolean => typeof navigator !== 'undefined' && /jsdom/i.test(navigator.userAgent);

/**
 * Mounts a Cytoscape instance in a div. Graph elements live inside Cytoscape (see
 * lib/graphController.ts); this component only owns its lifecycle.
 */
export function GraphCanvas({ onReady, onSelect }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const controller = useRef<GraphController | null>(null);
  const onSelectRef = useRef(onSelect);
  const dark = useIsDark();
  const darkRef = useRef(dark);

  useEffect(() => {
    onSelectRef.current = onSelect;
    darkRef.current = dark;
    controller.current?.setTheme(dark ? DARK_THEME : LIGHT_THEME);
  }, [onSelect, dark]);

  useEffect(() => {
    const c = createGraphController({
      container: host.current,
      headless: isJsdom(),
      onSelect: (id) => onSelectRef.current(id),
      theme: darkRef.current ? DARK_THEME : LIGHT_THEME,
    });
    controller.current = c;
    onReady(c);
    return () => {
      onReady(null);
      controller.current = null;
      c.destroy();
    };
  }, [onReady]);

  return (
    <div
      ref={host}
      className="graph-canvas"
      role="img"
      aria-label="Graph canvas"
      data-testid="graph-canvas"
    />
  );
}
