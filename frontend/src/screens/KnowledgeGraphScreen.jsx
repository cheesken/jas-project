import React, { useEffect, useRef, useState, useCallback } from 'react';
import * as d3 from 'd3';
import { COLORS, FONT } from '../ui';
import { api } from '../api';

const NODE_COLORS = {
  PERSON: '#7B4A27',
  ORG:    '#3a7d44',
  GPE:    '#2980b9',
  DATE:   '#8e44ad',
};

const ALL_TYPES = ['PERSON', 'ORG', 'GPE', 'DATE'];

function nodeRadius(mention_count) {
  return Math.max(6, Math.sqrt(mention_count || 1) * 5);
}

export default function KnowledgeGraphScreen() {
  const svgRef       = useRef(null);
  const containerRef = useRef(null);
  const simRef       = useRef(null);

  const [graphData,   setGraphData]   = useState(null);
  const [loading,     setLoading]     = useState(true);
  const [error,       setError]       = useState(null);
  const [activeTypes, setActiveTypes] = useState(new Set(ALL_TYPES));

  const fetchGraph = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api('/graph?limit=300');
      setGraphData(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchGraph(); }, [fetchGraph]);

  // Build / rebuild D3 simulation when data or type filters change.
  useEffect(() => {
    if (!graphData || !svgRef.current || !containerRef.current) return;
    if (simRef.current) simRef.current.stop();

    const filteredNodes = graphData.nodes.filter((n) => activeTypes.has(n.entity_type));
    const activeIds     = new Set(filteredNodes.map((n) => n.entity_id));
    const filteredEdges = graphData.edges.filter(
      (e) => activeIds.has(e.entity_a) && activeIds.has(e.entity_b),
    );

    const { width, height } = containerRef.current.getBoundingClientRect();
    if (!width || !height) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    if (filteredNodes.length === 0) return;

    const g = svg.append('g');

    svg.call(
      d3.zoom().scaleExtent([0.05, 4]).on('zoom', (e) => g.attr('transform', e.transform)),
    );

    const maxCo = Math.max(1, ...filteredEdges.map((e) => e.co_occurrence_count || 1));

    const linkSel = g.append('g')
      .selectAll('line')
      .data(filteredEdges)
      .enter().append('line')
      .attr('stroke', COLORS.border)
      .attr('stroke-width', (d) => 1 + ((d.co_occurrence_count || 1) / maxCo) * 2)
      .attr('stroke-opacity', (d) => 0.3 + ((d.co_occurrence_count || 1) / maxCo) * 0.5);

    const nodeGroup = g.append('g')
      .selectAll('g')
      .data(filteredNodes)
      .enter().append('g')
      .attr('cursor', 'pointer')
      .call(
        d3.drag()
          .on('start', (event, d) => {
            if (!event.active) sim.alphaTarget(0.3).restart();
            d.fx = d.x; d.fy = d.y;
          })
          .on('drag',  (event, d) => { d.fx = event.x; d.fy = event.y; })
          .on('end',   (event, d) => {
            if (!event.active) sim.alphaTarget(0);
            d.fx = null; d.fy = null;
          }),
      );

    nodeGroup.append('circle')
      .attr('r',            (d) => nodeRadius(d.mention_count))
      .attr('fill',         (d) => NODE_COLORS[d.entity_type] || COLORS.muted)
      .attr('fill-opacity', 0.85)
      .attr('stroke',       '#fff')
      .attr('stroke-width', 1.5);

    nodeGroup.append('text')
      .text((d) => d.name)
      .attr('text-anchor',    'middle')
      .attr('dy',             (d) => nodeRadius(d.mention_count) + 13)
      .attr('font-size',      '10px')
      .attr('font-family',    FONT)
      .attr('fill',           COLORS.text)
      .attr('fill-opacity',   0.8)
      .attr('pointer-events', 'none');

    // eslint-disable-next-line no-var
    var sim = d3.forceSimulation(filteredNodes)
      .force('link',      d3.forceLink(filteredEdges).id((d) => d.entity_id).distance(90).strength(0.5))
      .force('charge',    d3.forceManyBody().strength(-180))
      .force('center',    d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius((d) => nodeRadius(d.mention_count) + 6))
      .on('tick', () => {
        linkSel
          .attr('x1', (d) => d.source.x).attr('y1', (d) => d.source.y)
          .attr('x2', (d) => d.target.x).attr('y2', (d) => d.target.y);
        nodeGroup.attr('transform', (d) => `translate(${d.x},${d.y})`);
      });

    simRef.current = sim;
    return () => sim.stop();
  }, [graphData, activeTypes]);

  const toggleType = (type) => {
    setActiveTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) { if (next.size > 1) next.delete(type); }
      else next.add(type);
      return next;
    });
  };

  const hasNodes = !loading && !error && graphData?.nodes?.length > 0;

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', backgroundColor: COLORS.page, minHeight: 0, overflow: 'hidden', fontFamily: FONT }}>

      {/* ── Toolbar ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 16px', borderBottom: `1px solid ${COLORS.border}`, backgroundColor: COLORS.sidebar, flexShrink: 0, flexWrap: 'wrap' }}>
        <span style={{ fontSize: '13px', fontWeight: 600, color: COLORS.text, marginRight: '4px' }}>Show:</span>
        {ALL_TYPES.map((type) => (
          <button
            key={type}
            onClick={() => toggleType(type)}
            style={{
              padding: '3px 10px', borderRadius: '12px',
              border: `2px solid ${NODE_COLORS[type]}`,
              backgroundColor: activeTypes.has(type) ? NODE_COLORS[type] : 'transparent',
              color: activeTypes.has(type) ? '#fff' : NODE_COLORS[type],
              fontSize: '12px', fontWeight: 700, cursor: 'pointer', fontFamily: FONT,
            }}
          >
            {type}
          </button>
        ))}
      </div>

      {/* ── Graph area ── */}
      <div style={{ flex: 1, position: 'relative', minHeight: 0, overflow: 'hidden' }}>
        {loading && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: COLORS.muted, fontSize: '14px' }}>
            Loading knowledge graph…
          </div>
        )}
        {error && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '12px' }}>
            <span style={{ color: COLORS.bad, fontSize: '14px' }}>{error}</span>
            <button onClick={fetchGraph} style={{ background: 'none', border: 'none', color: COLORS.accent, textDecoration: 'underline', cursor: 'pointer', fontSize: '13px', fontFamily: FONT }}>Retry</button>
          </div>
        )}
        {!loading && !error && !hasNodes && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: COLORS.muted, fontSize: '14px', textAlign: 'center', padding: '40px' }}>
            No entities found. Ingest some documents to build the graph.
          </div>
        )}

        <div ref={containerRef} style={{ width: '100%', height: '100%' }}>
          <svg ref={svgRef} style={{ display: 'block', width: '100%', height: '100%' }} />
        </div>

        {/* Legend */}
        {hasNodes && (
          <div style={{ position: 'absolute', bottom: '16px', left: '16px', backgroundColor: 'rgba(255,255,255,0.92)', border: `1px solid ${COLORS.border}`, borderRadius: '8px', padding: '10px 14px', pointerEvents: 'none', display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {ALL_TYPES.map((type) => (
              <div key={type} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px', color: COLORS.text }}>
                <div style={{ width: '10px', height: '10px', borderRadius: '50%', backgroundColor: NODE_COLORS[type], flexShrink: 0 }} />
                {type}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
