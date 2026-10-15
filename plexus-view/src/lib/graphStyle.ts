import type { StylesheetJson } from 'cytoscape';

export interface Theme {
  text: string;
  textOutline: string;
  edge: string;
  edgeStrong: string;
  highlight: string;
}
export const LIGHT_THEME: Theme = {
  text: '#1f2933',
  textOutline: '#ffffff',
  edge: '#b7bfca',
  edgeStrong: '#5b6676',
  highlight: '#111827',
};
export const DARK_THEME: Theme = {
  text: '#e5e9f0',
  textOutline: '#14181f',
  edge: '#4a5465',
  edgeStrong: '#a7b1c2',
  highlight: '#f8fafc',
};

/** Ring colour of a suspect Fact (amber, readable on light and dark). */
export const SUSPECT_COLOR = '#d97706';

/** Above this many edges we switch to cheap haystack edges (no arrowheads). */
export const HAYSTACK_EDGE_THRESHOLD = 1500;

/** Default node-label width on the canvas (px); longer names are cut with an ellipsis. */
export const LABEL_MAX_WIDTH = 110;

export function buildStyle(
  theme: Theme,
  haystack: boolean,
  labelMaxWidth: number = LABEL_MAX_WIDTH,
): StylesheetJson {
  return [
    {
      selector: 'node',
      style: {
        width: 'data(size)',
        height: 'data(size)',
        'background-color': 'data(color)',
        label: 'data(display)',
        color: theme.text,
        'font-size': 10,
        'text-valign': 'bottom',
        'text-margin-y': 3,
        'text-wrap': 'ellipsis',
        'text-max-width': `${labelMaxWidth}px`,
        'text-outline-color': theme.textOutline,
        'text-outline-width': 2,
        'min-zoomed-font-size': 9,
      },
    },
    // P7: a Fact's opacity follows its activation (data.opacity is set only when the API sent one).
    { selector: 'node[opacity]', style: { opacity: 'data(opacity)' as unknown as number } },
    // P7: dormant = dashed outline; suspect = amber ring (the ⚠ glyph is in the label).
    {
      selector: 'node[?dormant]',
      style: { 'border-style': 'dashed' as const, 'border-width': 2, 'border-color': theme.edgeStrong },
    },
    { selector: 'node[?suspect]', style: { 'border-width': 2, 'border-color': SUSPECT_COLOR } },
    // Anchors keep their label even when zoomed out; everything else labels on zoom-in.
    {
      selector:
        'node[label = "Agent"], node[label = "Task"], node[label = "Decision"], node[label = "Entity"]',
      style: { 'min-zoomed-font-size': 0, 'font-size': 11, 'font-weight': 600 },
    },
    {
      selector: 'edge',
      style: haystack
        ? { width: 0.7, 'line-color': theme.edge, 'curve-style': 'haystack' as const }
        : {
            width: 1,
            'line-color': theme.edge,
            'target-arrow-color': theme.edge,
            'target-arrow-shape': 'triangle' as const,
            'arrow-scale': 0.7,
            'curve-style': 'bezier' as const,
          },
    },
    // Hovering a node shows its whole name (labels are ellipsised otherwise) above its neighbours.
    {
      selector: 'node.hover',
      style: {
        'text-wrap': 'wrap' as const,
        'text-max-width': '260px',
        'z-index': 999,
        'text-background-color': theme.textOutline,
        'text-background-opacity': 0.9,
        'text-background-padding': '2px',
        'min-zoomed-font-size': 0,
      },
    },
    { selector: '.hide-label, .hide-type', style: { display: 'none' as const } },
    { selector: 'node.dim, edge.dim', style: { opacity: 0.12 } },
    { selector: 'node.match', style: { 'border-width': 3, 'border-color': theme.highlight } },
    { selector: '.faded', style: { opacity: 0.1 } },
    {
      selector: 'node.nb',
      style: { opacity: 1 },
    },
    {
      selector: 'edge.nb',
      style: {
        opacity: 1,
        width: 2.2,
        'line-color': theme.edgeStrong,
        'target-arrow-color': theme.edgeStrong,
        'curve-style': 'bezier' as const,
        label: 'data(type)',
        'font-size': 8,
        color: theme.text,
        'text-rotation': 'autorotate' as const,
        'text-background-color': theme.textOutline,
        'text-background-opacity': 0.85,
        'text-background-padding': '1px',
      },
    },
    { selector: 'node.sel', style: { 'border-width': 4, 'border-color': theme.highlight, opacity: 1 } },
    {
      selector: 'node.fresh',
      style: { 'border-width': 5, 'border-color': '#22c55e', 'border-opacity': 0.9 },
    },
    { selector: 'node.ctx, edge.ctx', style: { opacity: 0.45 } },
    { selector: 'node.ev-created', style: { 'border-width': 5, 'border-color': '#22c55e', opacity: 1 } },
    { selector: 'node.ev-updated', style: { 'border-width': 5, 'border-color': '#f59e0b', opacity: 1 } },
    { selector: 'node.path', style: { 'border-width': 4, 'border-color': theme.highlight, opacity: 1 } },
    {
      selector: 'edge.path',
      style: {
        width: 4,
        'line-color': theme.highlight,
        'target-arrow-color': theme.highlight,
        'curve-style': 'bezier' as const,
        opacity: 1,
        'z-index': 99,
      },
    },
  ] as StylesheetJson;
}
