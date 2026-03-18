const GITHUB_URL = 'https://github.com/robin-scharf/gapbf'
const WEBSITE_URL = 'https://robinscharf.com/'
const WEBSITE_FAVICON = 'https://robinscharf.com/favicon.ico'
const GITHUB_ICON_PATH = [
  'M12 2C6.477 2 2 6.589 2 12.248c0 4.528 2.865 8.368 6.839 9.724',
  '.5.095.682-.221.682-.492 0-.244-.009-.891-.014-1.749',
  '-2.782.62-3.369-1.37-3.369-1.37-.455-1.179-1.11-1.493-1.11-1.493',
  '-.908-.636.069-.624.069-.624 1.004.072 1.532 1.054 1.532 1.054',
  '.892 1.567 2.341 1.114 2.91.852.091-.663.349-1.114.635-1.37',
  '-2.221-.259-4.555-1.137-4.555-5.06 0-1.118.389-2.033 1.029-2.75',
  '-.103-.259-.446-1.302.097-2.714 0 0 .84-.276 2.75 1.05',
  'A9.303 9.303 0 0 1 12 6.872a9.27 9.27 0 0 1 2.504.348',
  'c1.909-1.326 2.748-1.05 2.748-1.05.545 1.412.202 2.455.1 2.714',
  '.64.717 1.028 1.632 1.028 2.75 0 3.933-2.338 4.798-4.566 5.052',
  '.359.319.679.948.679 1.911 0 1.379-.012 2.491-.012 2.829',
  '0 .273.18.592.688.491C19.138 20.613 22 16.774 22 12.248',
  '22 6.589 17.523 2 12 2Z',
].join('')

function githubIcon() {
  return `
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" class="top-link-svg">
      <path
        fill="currentColor"
        d="${GITHUB_ICON_PATH}"
      />
    </svg>`
}

export function mountTopLinks(target) {
  if (!target) {
    return
  }

  target.innerHTML = `
    <nav class="top-links" aria-label="External links">
      <a class="top-link top-link-website" href="${WEBSITE_URL}" target="_blank" rel="noreferrer">
        <img class="top-link-favicon" src="${WEBSITE_FAVICON}" alt="robinscharf.com favicon" />
        <span>Author</span>
      </a>
      <a class="top-link top-link-github" href="${GITHUB_URL}" target="_blank" rel="noreferrer">
        ${githubIcon()}
        <span>GitHub</span>
      </a>
    </nav>`
}
