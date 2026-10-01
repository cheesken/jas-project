const FILE_TYPES = {
  pdf: 'pdf',
  txt: 'txt',
  png: 'image',
  jpg: 'image',
  jpeg: 'image',
};

export function getFileType(filePath) {
  const ext = filePath.split('.').pop().toLowerCase();
  return FILE_TYPES[ext] || null;
}
