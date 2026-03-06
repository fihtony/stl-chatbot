"use client";

interface IndexProgressCardProps {
  inProgress: boolean;
  progress: number;
  filesProcessed: number;
  totalFiles: number;
}

export function IndexProgressCard({ inProgress, progress, filesProcessed, totalFiles }: IndexProgressCardProps) {
  if (!inProgress) return null;

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h3 className="text-lg font-semibold mb-4">Creating Index</h3>

      <div className="mb-2">
        <div className="w-full bg-gray-200 rounded-full h-4">
          <div
            className="bg-blue-600 h-4 rounded-full transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      <div className="text-sm text-gray-600">
        Files: {filesProcessed} / {totalFiles}
      </div>
    </div>
  );
}
