import { useEffect, useId, useRef } from 'react';
import { createGraphController, DARK_THEME, LIGHT_THEME } from '../lib/graphController';
import type { ControllerOptions, GraphController } from '../lib/graphController';
import { useIsDark } from '../lib/theme';

interface Props {
  /** Called with the controller once mounted, and with null on unmount. Must be a stable function. */
  onReady: (c: GraphController | null) => void;
  onSelect: (id: string | null) => void;
  /** Layout / label tuning. Read once at mount: pass a constant. */
  tuning?: Pick<ControllerOptions, 'layout' | 'labelMaxWidth'>;
}

const isJsdom = (): boolean => typeof navigator !== 'undefined' && /jsdom/i.test(navigator.userAgent);

/**
 * Mounts a Cytoscape instance in a div. Graph elements live inside Cytoscape (see
 * lib/graphController.ts); this component only owns its lifecycle.
 */
export function GraphCanvas({ onReady, onSelect, tuning }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const descId = useId();
  const controller = useRef<GraphController | null>(null);
  const onSelectRef = useRef(onSelect);
  const dark = useIsDark();
  const darkRef = useRef(dark);
  const tuningRef = useRef(tuning);

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
      ...tuningRef.current,
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
    <>
      <div
        ref={host}
        className="graph-canvas"
        role="img"
        aria-label="Graph canvas"
        aria-describedby={descId}
        data-testid="graph-canvas"
      />
      <span id={descId} className="sr-only">
        A node-link drawing of the graph; it cannot be navigated with the keyboard. Use the search box to find
        a node, then read its properties and neighbours in the details panel.
      </span>
    </>
  );
}
