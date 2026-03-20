export async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!response.ok) {
    const payload = await response
      .json()
      .catch(() => ({ detail: [response.statusText] }))
    const detail = Array.isArray(payload.detail)
      ? payload.detail.join(' | ')
      : payload.detail
    throw new Error(detail || response.statusText)
  }
  return response.json()
}

export async function writeClipboardText(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }

  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'absolute'
  textarea.style.left = '-9999px'
  document.body.append(textarea)
  textarea.select()

  try {
    const copied = document.execCommand('copy')
    if (!copied) {
      throw new Error('Copy command was rejected by the browser')
    }
  } finally {
    textarea.remove()
  }
}

function escapeCsvValue(value) {
  const text = value == null ? '' : String(value)
  return `"${text.replaceAll('"', '""')}"`
}

export function downloadTextFile(filename, text, mimeType) {
  const blob = new Blob([text], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 0)
}

export function buildCsv(rows) {
  return rows
    .map((row) => row.map((value) => escapeCsvValue(value)).join(','))
    .join('\n')
}
