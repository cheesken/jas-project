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

export async function importChromeHistory(showToast) {
  let filePath;
  if (window.electronAPI) {
    filePath = await window.electronAPI.findChromeHistory();
    if (!filePath) {
      showToast('Chrome history not found. Is Google Chrome installed?', 'error');
      return;
    }
  } else {
    filePath = prompt('Enter the path to Chrome\'s History file (Electron not available):');
    if (!filePath) return;
  }
  await postIngest(filePath, 'browser_history', 'Chrome history', showToast);
}
