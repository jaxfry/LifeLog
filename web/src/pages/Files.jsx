import { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { 
  Upload, 
  FileText, 
  Image as ImageIcon, 
  X, 
  CheckCircle, 
  Loader2, 
  Search,
  Filter,
  MoreVertical,
  Download,
  Tag
} from 'lucide-react';
import { filesAPI } from '../services/api';
import { format } from 'date-fns';

const Files = () => {
  const [dragActive, setDragActive] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [category, setCategory] = useState('');
  const [tags, setTags] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const fileInputRef = useRef(null);
  const queryClient = useQueryClient();

  // Fetch files
  const { data: files = [], isLoading } = useQuery({
    queryKey: ['files', searchQuery],
    queryFn: () => filesAPI.listFiles({ q: searchQuery }),
  });

  // Upload mutation
  const uploadMutation = useMutation({
    mutationFn: async ({ file, metadata }) => {
      return filesAPI.uploadFile(file, metadata);
    },
    onSuccess: () => {
      queryClient.invalidateQueries(['files']);
    },
  });

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFiles(e.dataTransfer.files);
    }
  };

  const handleChange = (e) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      handleFiles(e.target.files);
    }
  };

  const handleFiles = (files) => {
    const newFiles = Array.from(files).map(file => ({
      file,
      id: Math.random().toString(36).substring(7),
      status: 'pending', // pending, uploading, success, error
      progress: 0
    }));
    setSelectedFiles(prev => [...prev, ...newFiles]);
  };

  const removeFile = (id) => {
    setSelectedFiles(prev => prev.filter(f => f.id !== id));
  };

  const handleUpload = async () => {
    setUploading(true);
    
    for (let i = 0; i < selectedFiles.length; i++) {
      const fileObj = selectedFiles[i];
      if (fileObj.status === 'success') continue;

      try {
        // Update status to uploading
        setSelectedFiles(prev => prev.map(f => 
          f.id === fileObj.id ? { ...f, status: 'uploading' } : f
        ));

        await uploadMutation.mutateAsync({
          file: fileObj.file,
          metadata: {
            category: category || 'document',
            tags: tags,
            description: `Uploaded via Web UI`
          }
        });

        // Update status to success
        setSelectedFiles(prev => prev.map(f => 
          f.id === fileObj.id ? { ...f, status: 'success' } : f
        ));
      } catch (error) {
        console.error("Upload failed", error);
        setSelectedFiles(prev => prev.map(f => 
          f.id === fileObj.id ? { ...f, status: 'error' } : f
        ));
      }
    }
    setUploading(false);
    // Clear successful uploads after a delay? No, let user clear them.
  };

  const getFileIcon = (mimeType) => {
    if (mimeType.startsWith('image/')) return <ImageIcon className="text-purple-500" size={20} />;
    if (mimeType === 'application/pdf') return <FileText className="text-red-500" size={20} />;
    return <FileText className="text-gray-500" size={20} />;
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">File Manager</h1>
          <p className="text-gray-500">Upload and manage your digital assets with AI analysis</p>
        </div>
      </div>

      {/* Upload Area */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        <div className="p-6">
          <div 
            className={`relative border-2 border-dashed rounded-xl p-8 text-center transition-colors ${
              dragActive ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-gray-400'
            }`}
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
          >
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={handleChange}
            />
            
            <div className="flex flex-col items-center gap-3">
              <div className="p-3 bg-blue-100 text-blue-600 rounded-full">
                <Upload size={24} />
              </div>
              <div>
                <p className="text-lg font-medium text-gray-900">
                  Drop files here or click to upload
                </p>
                <p className="text-sm text-gray-500 mt-1">
                  Support for Images, PDFs, and Text files
                </p>
              </div>
              <button 
                onClick={() => fileInputRef.current?.click()}
                className="mt-2 px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
              >
                Select Files
              </button>
            </div>
          </div>

          {/* Selected Files List */}
          {selectedFiles.length > 0 && (
            <div className="mt-6 space-y-4">
              <div className="flex gap-4 mb-4">
                <div className="flex-1">
                  <label className="block text-sm font-medium text-gray-700 mb-1">Category</label>
                  <select 
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                    className="w-full rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                  >
                    <option value="">Select Category...</option>
                    <option value="document">Document</option>
                    <option value="image">Image</option>
                    <option value="receipt">Receipt</option>
                    <option value="screenshot">Screenshot</option>
                    <option value="other">Other</option>
                  </select>
                </div>
                <div className="flex-[2]">
                  <label className="block text-sm font-medium text-gray-700 mb-1">Tags (comma separated)</label>
                  <input
                    type="text"
                    value={tags}
                    onChange={(e) => setTags(e.target.value)}
                    placeholder="work, project, important"
                    className="w-full rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                  />
                </div>
              </div>

              <div className="border rounded-lg divide-y">
                {selectedFiles.map((fileObj) => (
                  <div key={fileObj.id} className="flex items-center justify-between p-3 bg-gray-50">
                    <div className="flex items-center gap-3">
                      {getFileIcon(fileObj.file.type)}
                      <div>
                        <p className="text-sm font-medium text-gray-900">{fileObj.file.name}</p>
                        <p className="text-xs text-gray-500">{(fileObj.file.size / 1024).toFixed(1)} KB</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      {fileObj.status === 'uploading' && <Loader2 className="animate-spin text-blue-500" size={18} />}
                      {fileObj.status === 'success' && <CheckCircle className="text-green-500" size={18} />}
                      {fileObj.status === 'error' && <span className="text-red-500 text-sm">Failed</span>}
                      
                      {fileObj.status !== 'uploading' && (
                        <button 
                          onClick={() => removeFile(fileObj.id)}
                          className="text-gray-400 hover:text-red-500"
                        >
                          <X size={18} />
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex justify-end gap-3">
                <button
                  onClick={() => setSelectedFiles([])}
                  className="px-4 py-2 text-gray-600 hover:text-gray-800"
                  disabled={uploading}
                >
                  Clear All
                </button>
                <button
                  onClick={handleUpload}
                  disabled={uploading || selectedFiles.every(f => f.status === 'success')}
                  className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {uploading ? (
                    <>
                      <Loader2 className="animate-spin" size={18} />
                      Uploading...
                    </>
                  ) : (
                    <>
                      <Upload size={18} />
                      Upload {selectedFiles.filter(f => f.status !== 'success').length} Files
                    </>
                  )}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* File List */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200">
        <div className="p-4 border-b border-gray-200 flex justify-between items-center">
          <h2 className="font-semibold text-gray-900">Recent Files</h2>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={18} />
            <input
              type="text"
              placeholder="Search files..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10 pr-4 py-2 border border-gray-300 rounded-lg text-sm focus:ring-blue-500 focus:border-blue-500 w-64"
            />
          </div>
        </div>
        
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-gray-50 text-gray-600 font-medium">
              <tr>
                <th className="px-6 py-3">Name</th>
                <th className="px-6 py-3">Category</th>
                <th className="px-6 py-3">AI Status</th>
                <th className="px-6 py-3">Date</th>
                <th className="px-6 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {isLoading ? (
                <tr>
                  <td colSpan="5" className="px-6 py-8 text-center text-gray-500">
                    <Loader2 className="animate-spin mx-auto mb-2" size={24} />
                    Loading files...
                  </td>
                </tr>
              ) : files.length === 0 ? (
                <tr>
                  <td colSpan="5" className="px-6 py-8 text-center text-gray-500">
                    No files found. Upload some files to get started.
                  </td>
                </tr>
              ) : (
                files.map((file) => (
                  <tr key={file.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div className="p-2 bg-gray-100 rounded-lg">
                          {getFileIcon(file.mime_type)}
                        </div>
                        <div>
                          <p className="font-medium text-gray-900 truncate max-w-xs" title={file.filename}>
                            {file.filename}
                          </p>
                          <p className="text-xs text-gray-500">
                            {(file.size_bytes / 1024).toFixed(1)} KB
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      {file.category ? (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                          {file.category}
                        </span>
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      {file.is_processed ? (
                        <div className="flex items-center gap-1.5 text-green-600">
                          <CheckCircle size={16} />
                          <span className="text-xs font-medium">Analyzed</span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1.5 text-amber-600">
                          <Loader2 size={16} className="animate-spin" />
                          <span className="text-xs font-medium">Processing</span>
                        </div>
                      )}
                      {file.ai_metadata?.keywords && (
                        <div className="mt-1 flex flex-wrap gap-1">
                          {file.ai_metadata.keywords.slice(0, 3).map((k, i) => (
                            <span key={i} className="text-[10px] bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">
                              {k}
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="px-6 py-4 text-gray-500">
                      {format(new Date(file.created_at), 'MMM d, yyyy HH:mm')}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <button className="text-gray-400 hover:text-gray-600 p-1">
                        <MoreVertical size={18} />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default Files;
