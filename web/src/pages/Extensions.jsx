import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef } from 'react';
import { extensionsAPI } from '../services/api';
import { Package, Download, CheckCircle, XCircle, Info, Upload } from 'lucide-react';

const Extensions = () => {
  const queryClient = useQueryClient();
  const fileInputRef = useRef(null);

  const { data: extensions = [], isLoading, isError } = useQuery({
    queryKey: ['extensions'],
    queryFn: extensionsAPI.getExtensions,
  });

  const handleUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    try {
      await extensionsAPI.uploadExtension(file);
      queryClient.invalidateQueries(['extensions']);
      alert('Extension uploaded successfully!');
    } catch (error) {
      console.error('Failed to upload extension:', error);
      alert('Failed to upload extension. ' + (error.response?.data?.detail || error.message));
    } finally {
      event.target.value = '';
    }
  };

  const handleDownload = async (extensionId) => {
    try {
      const blob = await extensionsAPI.downloadExtension(extensionId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${extensionId}.zip`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      console.error('Failed to download extension:', error);
      // Using alert for simplicity; in production, consider a toast notification system
      alert('Failed to download extension. Please try again.');
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-96">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="max-w-6xl mx-auto">
        <div className="bg-red-50 border border-red-200 text-red-700 p-6 rounded-lg">
          <p className="font-semibold mb-2">Error loading extensions</p>
          <p className="text-sm">Please check your API connection and try again.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto">
      {/* Header */}
      <div className="mb-8 flex justify-between items-start">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Extensions</h1>
          <p className="text-gray-600">Extend LifeLog capabilities with powerful data collectors</p>
        </div>
        <div>
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleUpload}
            className="hidden"
            accept=".zip"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            className="btn-primary flex items-center gap-2"
          >
            <Upload size={20} />
            Upload Extension
          </button>
        </div>
      </div>

      {/* Info Card */}
      <div className="card mb-8 bg-blue-50 border-2 border-blue-200">
        <div className="flex items-start gap-3">
          <Info className="text-blue-600 flex-shrink-0 mt-1" size={20} />
          <div>
            <h3 className="font-semibold text-gray-900 mb-2">About Extensions</h3>
            <p className="text-sm text-gray-700">
              Extensions are modular data collectors that gather information from various sources. 
              They run on your devices and automatically send data to your LifeLog server.
            </p>
            <div className="mt-3 text-sm text-gray-700">
              <strong>How to install:</strong>
              <ol className="list-decimal list-inside mt-1 space-y-1 ml-2">
                <li>Download the extension package using the download button</li>
                <li>Extract the ZIP file to your LifeLog client's extensions directory</li>
                <li>Restart your LifeLog client to activate the extension</li>
                <li>Configure the extension settings in the manifest.json file if needed</li>
              </ol>
            </div>
          </div>
        </div>
      </div>

      {/* Extensions Grid */}
      {extensions.length === 0 ? (
        <div className="card text-center py-12">
          <Package className="mx-auto mb-4 text-gray-400" size={48} />
          <p className="text-gray-600 text-lg mb-4">No extensions available</p>
          <p className="text-gray-500 text-sm">Extensions will appear here when added to the server</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {extensions.map((extension) => {
            const config = typeof extension.config === 'string' 
              ? JSON.parse(extension.config) 
              : extension.config;

            return (
              <div key={extension.id} className="card hover:shadow-lg transition-shadow">
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-start gap-3">
                    <div className={`w-12 h-12 rounded-lg flex items-center justify-center ${
                      extension.is_active ? 'bg-green-100' : 'bg-gray-100'
                    }`}>
                      <Package className={extension.is_active ? 'text-green-600' : 'text-gray-600'} size={24} />
                    </div>
                    <div>
                      <h3 className="text-lg font-semibold text-gray-900">{extension.id}</h3>
                      <p className="text-sm text-gray-500">Version {extension.version}</p>
                    </div>
                  </div>

                  {/* Status Badge */}
                  <div>
                    {extension.is_active ? (
                      <span className="flex items-center gap-1 px-2 py-1 bg-green-100 text-green-700 rounded-full text-xs font-medium">
                        <CheckCircle size={12} />
                        Active
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 px-2 py-1 bg-gray-100 text-gray-600 rounded-full text-xs font-medium">
                        <XCircle size={12} />
                        Inactive
                      </span>
                    )}
                  </div>
                </div>

                {/* Extension Details */}
                <div className="mb-4">
                  {config?.description && (
                    <p className="text-sm text-gray-700 mb-3">{config.description}</p>
                  )}
                  
                  {config?.client && (
                    <div className="bg-gray-50 rounded-lg p-3 text-sm">
                      <div className="flex justify-between mb-1">
                        <span className="text-gray-600">Type:</span>
                        <span className="text-gray-900 font-medium capitalize">{config.client.type || 'Unknown'}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-600">Entry File:</span>
                        <span className="text-gray-900 font-mono text-xs">{config.client.file || 'N/A'}</span>
                      </div>
                    </div>
                  )}
                </div>

                {/* Actions */}
                <div className="border-t border-gray-200 pt-4">
                  <button
                    onClick={() => handleDownload(extension.id)}
                    className="btn-primary w-full flex items-center justify-center gap-2"
                  >
                    <Download size={18} />
                    Download Extension
                  </button>
                </div>

                {/* Additional Info */}
                {config?.requires && (
                  <div className="mt-3 text-xs text-gray-500">
                    <strong>Requirements:</strong> {Array.isArray(config.requires) ? config.requires.join(', ') : config.requires}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Development Info */}
      <div className="mt-8 card bg-gray-50">
        <h3 className="font-semibold text-gray-900 mb-3">Developing Extensions</h3>
        <p className="text-sm text-gray-700 mb-3">
          Want to create your own extension? Extensions are Python modules that collect data from various sources.
        </p>
        <div className="text-sm text-gray-700">
          <strong>Basic extension structure:</strong>
          <ul className="list-disc list-inside mt-2 space-y-1 ml-2">
            <li><code className="bg-white px-1 rounded">manifest.json</code> - Extension metadata and configuration</li>
            <li><code className="bg-white px-1 rounded">collector.py</code> - Main data collection logic</li>
            <li><code className="bg-white px-1 rounded">processor.py</code> (optional) - Server-side data processing</li>
          </ul>
        </div>
        <p className="text-sm text-gray-600 mt-3">
          Place your extension folder in <code className="bg-white px-2 py-1 rounded">server/extensions/</code> on the server, 
          and it will be automatically discovered and made available for download.
        </p>
      </div>
    </div>
  );
};

export default Extensions;
