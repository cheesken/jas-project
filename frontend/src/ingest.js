import { getFileType } from './fileTypes';

const INGEST_URL = 'http://localhost:8000/ingest';

async function postIngest(filePath, fileType, label, showToast) {
  showToast(`Uploading ${label}...`, 'info');
  try {
    const res = await fetch(INGEST_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: filePath, file_type: fileType }),
    });
    if (res.status === 201) {
      showToast(`${label} is being indexed.`, 'success');
    } else if (res.status === 409) {
      showToast(`${label} is already indexed.`, 'info');
    } else if (res.status === 403) {
      // e.g. Safari history without Full Disk Access; the API explains what to grant.
      const body = await res.json().catch(() => ({}));
      showToast(typeof body.detail === 'string' ? body.detail : `Permission denied reading ${label}.`, 'error');
    } else {
      showToast(`Failed to upload ${label}. Please try again.`, 'error');
    }
  } catch (err) {
    showToast(`Failed to upload ${label}. Please try again.`, 'error');
  }
}

export async function uploadFile(showToast) {
  let filePath;
  if (window.electronAPI) {
    filePath = await window.electronAPI.openPdfFile();
  } else {
    // Fallback for browser dev: prompt for path
    filePath = prompt('Enter PDF, TXT or image file path (Electron not available):');
  }
  if (!filePath) return;

  const fileName = filePath.split('/').pop();
  const fileType = getFileType(filePath);
  if (!fileType) {
    showToast(`${fileName} is not a supported file type.`, 'error');
    return;
  }
  await postIngest(filePath, fileType, fileName, showToast);
}

const BROWSERS = {
  chrome: { label: 'Chrome history', find: () => window.electronAPI.findChromeHistory(),
    missing: 'Chrome history not found. Is Google Chrome installed?' },
  safari: { label: 'Safari history', find: () => window.electronAPI.findSafariHistory(),
    missing: 'Safari history not found. Safari history is only available on macOS.' },
};

// Chrome and Safari both post file_type "browser_history"; the backend detects
// which browser the database came from.
async function importBrowserHistory(browser, showToast) {
  const { label, find, missing } = BROWSERS[browser];
  let filePath;
  if (window.electronAPI) {
    filePath = await find();
    if (!filePath) {
      showToast(missing, 'error');
      return;
    }
  } else {
    filePath = prompt(`Enter the path to the ${label} file (Electron not available):`);
    if (!filePath) return;
  }
  await postIngest(filePath, 'browser_history', label, showToast);
}

export const importChromeHistory = (showToast) => importBrowserHistory('chrome', showToast);
export const importSafariHistory = (showToast) => importBrowserHistory('safari', showToast);

// Safari exists only on macOS; hide its buttons elsewhere.
export const safariAvailable = () => window.electronAPI?.platform === 'darwin';
