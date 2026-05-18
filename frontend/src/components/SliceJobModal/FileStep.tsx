import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { FileBox, Loader2, Search } from 'lucide-react';
import { api, type LibraryFileListItem } from '../../api/client';

interface FileStepProps {
  selectedFileId: number | null;
  onSelect: (file: LibraryFileListItem) => void;
}

export function FileStep({ selectedFileId, onSelect }: FileStepProps) {
  const [search, setSearch] = useState('');

  const { data: files, isLoading } = useQuery({
    queryKey: ['library-files-slice-picker'],
    queryFn: () => api.getLibraryFiles(null, false),
  });

  const filtered = (files ?? []).filter((f) =>
    f.filename.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="flex flex-col gap-3">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
        <input
          type="text"
          placeholder="Search files…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-9 pr-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
        />
      </div>

      {isLoading ? (
        <div className="flex justify-center py-8">
          <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center gap-2 py-8 text-gray-500">
          <FileBox className="w-8 h-8" />
          <p className="text-sm">{search ? 'No files match' : 'No library files'}</p>
        </div>
      ) : (
        <div className="flex flex-col gap-1 max-h-80 overflow-y-auto pr-1">
          {filtered.map((f) => (
            <button
              key={f.id}
              onClick={() => onSelect(f)}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-left transition-colors ${
                selectedFileId === f.id
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-800 hover:bg-gray-700 text-gray-200'
              }`}
            >
              {f.thumbnail_path ? (
                <img
                  src={api.getLibraryFileThumbnailUrl(f.id)}
                  alt=""
                  className="w-10 h-10 rounded object-cover flex-shrink-0"
                />
              ) : (
                <div className="w-10 h-10 rounded bg-gray-700 flex items-center justify-center flex-shrink-0">
                  <FileBox className="w-5 h-5 text-gray-500" />
                </div>
              )}
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium truncate">{f.filename}</p>
                <p className="text-xs text-gray-400 truncate">{f.file_type.toUpperCase()}</p>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
