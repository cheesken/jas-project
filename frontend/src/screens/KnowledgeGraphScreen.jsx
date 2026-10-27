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

  const [graphData,      setGraphData]      = useState(null);
  const [loading,        setLoading]        = useState(true);
  const [error,          setError]          = useState(null);
  const [activeTypes,    setActiveTypes]    = useState(new Set(ALL_TYPES));
  const [minMentions,    setMinMentions]    = useState(1);
  const [searchQuery,    setSearchQuery]    = useState('');
  const [highlightedIds,  setHighlightedIds]  = useState(null); // null = no active search
  const [searchResults,   setSearchResults]   = useState([]);   // for dropdown
  const [searchFocused,   setSearchFocused]   = useState(false);
  const [selectedId,     setSelectedId]     = useState(null);
  const [entityDetail,   setEntityDetail]   = useState(null);
  const [detailLoading,  setDetailLoading]  = useState(false);
  const [panelTab,       setPanelTab]       = useState('details'); // 'details' | 'docs'

  const fetchGraph = useCallback(async (minM = 1) => {
    setLoading(true);
    setError(null);
    try {
      const data = await api(`/graph?limit=300&min_mentions=${minM}`);
      setGraphData(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchGraph(minMentions); }, [fetchGraph, minMentions]);

  // Debounced search: highlight matching nodes + populate dropdown results.
  useEffect(() => {
    if (!searchQuery.trim()) {
      setHighlightedIds(null);
      setSearchResults([]);
      return;
    }
    const t = setTimeout(async () => {
      try {
        const data = await api(`/graph/search?q=${encodeURIComponent(searchQuery)}&limit=20`);
        setHighlightedIds(new Set(data.results.map((r) => r.entity_id)));
        setSearchResults(data.results);
      } catch {
        setHighlightedIds(null);
        setSearchResults([]);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [searchQuery]);

  // Fetch entity detail when a node is selected.
  useEffect(() => {
    if (!selectedId) { setEntityDetail(null); return; }
    setPanelTab('details');
    setDetailLoading(true);
    api(`/graph/${encodeURIComponent(selectedId)}`)
      .then((data) => setEntityDetail(data))
      .catch(() => setEntityDetail(null))
      .finally(() => setDetailLoading(false));
  }, [selectedId]);

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

    // Click SVG background to deselect.
    svg.on('click', () => setSelectedId(null));

    const nodeGroup = g.append('g')
      .selectAll('g')
      .data(filteredNodes)
      .enter().append('g')
      .attr('cursor', 'pointer')
      .on('click', (event, d) => {
        event.stopPropagation();
        setSelectedId((prev) => (prev === d.entity_id ? null : d.entity_id));
      })
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

  // Update selected node stroke without restarting simulation.
  useEffect(() => {
    if (!svgRef.current) return;
    d3.select(svgRef.current).selectAll('circle')
      .attr('stroke',       (d) => d.entity_id === selectedId ? COLORS.text : '#fff')
      .attr('stroke-width', (d) => d.entity_id === selectedId ? 3 : 1.5);
  }, [selectedId]);

  // Update node/label opacity when search highlight changes — no simulation restart needed.
  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);
    svg.selectAll('circle').attr('fill-opacity', (d) =>
      !highlightedIds ? 0.85 : (highlightedIds.has(d.entity_id) ? 1 : 0.12),
    );
    svg.selectAll('text').attr('fill-opacity', (d) =>
      !highlightedIds ? 0.8 : (highlightedIds.has(d.entity_id) ? 1 : 0.1),
    );
  }, [highlightedIds]);

  const jumpToEntity = (entityId) => {
    setSelectedId(entityId);
    setSearchQuery('');
    setSearchResults([]);
    setHighlightedIds(null);
    setSearchFocused(false);
  };

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
        {/* Search with results dropdown */}
        <div style={{ flex: 1, minWidth: '140px', position: 'relative' }}>
          <input
            type="text"
            placeholder="Search entities…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onFocus={() => setSearchFocused(true)}
            onBlur={() => setTimeout(() => setSearchFocused(false), 150)}
            style={{ width: '100%', boxSizing: 'border-box', padding: '5px 10px', borderRadius: '6px', border: `1px solid ${COLORS.border}`, fontSize: '13px', fontFamily: FONT, backgroundColor: COLORS.card, color: COLORS.text, outline: 'none' }}
          />
          {/* Dropdown */}
          {searchFocused && searchResults.length > 0 && (
            <div style={{ position: 'absolute', top: 'calc(100% + 4px)', left: 0, right: 0, backgroundColor: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: '8px', boxShadow: '0 4px 16px rgba(0,0,0,0.12)', zIndex: 100, maxHeight: '260px', overflowY: 'auto' }}>
              {searchResults.map((r) => (
                <div
                  key={r.entity_id}
                  onMouseDown={() => jumpToEntity(r.entity_id)}
                  style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 12px', cursor: 'pointer', borderBottom: `1px solid ${COLORS.border}` }}
                  onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = COLORS.page; }}
                  onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = ''; }}
                >
                  <div style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: NODE_COLORS[r.entity_type] || COLORS.muted, flexShrink: 0 }} />
                  <span style={{ flex: 1, fontSize: '13px', color: COLORS.text, fontFamily: FONT, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.name}</span>
                  <span style={{ fontSize: '11px', color: COLORS.muted, fontFamily: FONT, flexShrink: 0 }}>{r.entity_type} · {r.mention_count}×</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Entity type toggles */}
        <span style={{ fontSize: '13px', fontWeight: 600, color: COLORS.text }}>Show:</span>
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

        {/* Min mentions */}
        <span style={{ fontSize: '12px', color: COLORS.muted, whiteSpace: 'nowrap' }}>Min mentions</span>
        <input
          type="number"
          min="1"
          value={minMentions}
          onChange={(e) => { const v = parseInt(e.target.value, 10); if (!isNaN(v) && v >= 1) setMinMentions(v); }}
          style={{ width: '48px', padding: '4px 8px', borderRadius: '6px', border: `1px solid ${COLORS.border}`, fontSize: '13px', fontFamily: FONT, backgroundColor: COLORS.card, color: COLORS.text, outline: 'none' }}
        />
      </div>

      {/* ── Graph area + detail panel ── */}
      <div style={{ flex: 1, display: 'flex', minHeight: 0, overflow: 'hidden' }}>

      {/* Graph canvas */}
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

      {/* ── Detail panel ── */}
      {selectedId && (
        <div style={{ width: '290px', flexShrink: 0, borderLeft: `1px solid ${COLORS.border}`, backgroundColor: COLORS.card, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {detailLoading ? (
            <div style={{ padding: '24px', color: COLORS.muted, fontSize: '13px', fontFamily: FONT }}>Loading…</div>
          ) : entityDetail ? (
            <>
              {/* Header */}
              <div style={{ padding: '14px 16px 10px', borderBottom: `1px solid ${COLORS.border}`, flexShrink: 0 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                  <h2 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: COLORS.text, wordBreak: 'break-word', fontFamily: FONT, lineHeight: 1.3 }}>{entityDetail.entity.name}</h2>
                  <button onClick={() => setSelectedId(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: COLORS.muted, fontSize: '18px', padding: '0 0 0 8px', lineHeight: 1, flexShrink: 0 }}>×</button>
                </div>
                <div style={{ display: 'inline-block', padding: '2px 8px', borderRadius: '10px', backgroundColor: NODE_COLORS[entityDetail.entity.entity_type] || COLORS.muted, color: '#fff', fontSize: '11px', fontWeight: 700, fontFamily: FONT }}>
                  {entityDetail.entity.entity_type}
                </div>
              </div>

              {/* Tab bar */}
              <div style={{ display: 'flex', borderBottom: `1px solid ${COLORS.border}`, flexShrink: 0 }}>
                {[
                  ['details', 'Details'],
                  ['docs', `Documents${entityDetail.docs?.length ? ` (${entityDetail.docs.length})` : ''}`],
                ].map(([id, label]) => (
                  <button
                    key={id}
                    onClick={() => setPanelTab(id)}
                    style={{ flex: 1, padding: '8px 4px', background: 'none', border: 'none', borderBottom: panelTab === id ? `2px solid ${COLORS.accent}` : '2px solid transparent', color: panelTab === id ? COLORS.accent : COLORS.muted, fontSize: '12px', fontWeight: 600, fontFamily: FONT, cursor: 'pointer', marginBottom: '-1px' }}
                  >
                    {label}
                  </button>
                ))}
              </div>

              {/* Tab body */}
              <div style={{ flex: 1, overflowY: 'auto', padding: '14px 16px' }}>

                {panelTab === 'details' && (
                  <>
                    {/* Stats */}
                    {[
                      ['Mentions', entityDetail.entity.mention_count],
                      ['Documents', entityDetail.entity.doc_count ?? entityDetail.docs?.length ?? '—'],
                    ].map(([label, val]) => (
                      <div key={label} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px', fontSize: '13px', fontFamily: FONT }}>
                        <span style={{ color: COLORS.muted }}>{label}</span>
                        <span style={{ color: COLORS.text, fontWeight: 600 }}>{val}</span>
                      </div>
                    ))}

                    {/* Neighbors */}
                    {entityDetail.neighbors?.length > 0 && (
                      <>
                        <div style={{ fontSize: '11px', fontWeight: 700, color: COLORS.muted, textTransform: 'uppercase', letterSpacing: '0.5px', marginTop: '16px', marginBottom: '8px', fontFamily: FONT }}>Co-occurs with</div>
                        {entityDetail.neighbors.slice(0, 12).map((n) => (
                          <div
                            key={n.entity_id}
                            onClick={() => setSelectedId(n.entity_id)}
                            style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 8px', borderRadius: '6px', marginBottom: '3px', cursor: 'pointer', backgroundColor: COLORS.page, fontSize: '13px', color: COLORS.text, fontFamily: FONT }}
                          >
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', overflow: 'hidden' }}>
                              <div style={{ width: '7px', height: '7px', borderRadius: '50%', backgroundColor: NODE_COLORS[n.entity_type] || COLORS.muted, flexShrink: 0 }} />
                              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{n.name}</span>
                            </div>
                            <span style={{ color: COLORS.muted, fontSize: '11px', flexShrink: 0, marginLeft: '6px' }}>{n.co_occurrence_count}×</span>
                          </div>
                        ))}
                      </>
                    )}
                  </>
                )}

                {panelTab === 'docs' && (
                  <>
                    {entityDetail.docs?.length > 0 ? (
                      entityDetail.docs.map((doc, i) => {
                        const parts = (doc.file_name || '').replace(/\\/g, '/').split('/');
                        const basename = parts[parts.length - 1] || doc.file_name;
                        const dir = parts.length > 1 ? parts.slice(0, -1).join('/') : null;
                        return (
                          <div key={i} style={{ padding: '10px 12px', borderRadius: '8px', marginBottom: '6px', backgroundColor: COLORS.page, border: `1px solid ${COLORS.border}` }}>
                            <div style={{ fontSize: '13px', fontWeight: 600, color: COLORS.text, fontFamily: FONT, wordBreak: 'break-word', marginBottom: dir ? '3px' : 0 }}>
                              {basename}
                            </div>
                            {dir && (
                              <div style={{ fontSize: '11px', color: COLORS.muted, fontFamily: FONT, wordBreak: 'break-all' }}>{dir}</div>
                            )}
                          </div>
                        );
                      })
                    ) : (
                      <div style={{ color: COLORS.muted, fontSize: '13px', fontFamily: FONT }}>No source documents recorded.</div>
                    )}
                  </>
                )}

              </div>
            </>
          ) : null}
        </div>
      )}

      </div>{/* end graph area + detail panel */}
    </div>
  );
}
