// Preact + htm binding — the whole UI renders through this `html` tag.
import { h } from 'preact'
import htm from 'htm'

export { h, render, Fragment } from 'preact'
export { useState, useEffect, useRef, useMemo, useCallback } from 'preact/hooks'
export const html = htm.bind(h)
