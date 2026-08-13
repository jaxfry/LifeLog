import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { devicesAPI, analyticsAPI } from '../services/api';
import { Monitor, Laptop, Smartphone, Tablet, Server, Plus, Trash2, RefreshCw, Activity, AlertCircle } from 'lucide-react';

const deviceIcons = {
  desktop: Monitor,
  laptop: Laptop,
  mobile: Smartphone,
  tablet: Tablet,
  server: Server,
};

const Devices = () => {
  const [showAddDevice, setShowAddDevice] = useState(false);
  const [newDeviceName, setNewDeviceName] = useState('');
  const [newDeviceType, setNewDeviceType] = useState('desktop');
  const queryClient = useQueryClient();

  // Devices
  const { data: devices = [], isLoading: devicesLoading } = useQuery({
    queryKey: ['devices'],
    queryFn: devicesAPI.getDevices,
  });

  // Collector stats
  const { data: collectorStats = [], isLoading: statsLoading } = useQuery({
    queryKey: ['collector-stats'],
    queryFn: analyticsAPI.getCollectorStats,
  });

  const createDeviceMutation = useMutation({
    mutationFn: (device) => devicesAPI.createDevice(device),
    onSuccess: () => {
      queryClient.invalidateQueries(['devices']);
      queryClient.invalidateQueries(['collector-stats']);
      setShowAddDevice(false);
      setNewDeviceName('');
      setNewDeviceType('desktop');
    },
  });

  const deleteDeviceMutation = useMutation({
    mutationFn: (deviceId) => devicesAPI.deleteDevice(deviceId),
    onSuccess: () => {
      queryClient.invalidateQueries(['devices']);
      queryClient.invalidateQueries(['collector-stats']);
    },
  });

  const rotateKeyMutation = useMutation({
    mutationFn: (deviceId) => devicesAPI.rotateKey(deviceId),
    onSuccess: () => {
      queryClient.invalidateQueries(['devices']);
    },
  });

  const handleAddDevice = () => {
    if (newDeviceName.trim()) {
      const id = newDeviceName
        .toLowerCase()
        .replace(/[^a-z0-9-]/g, '-')
        .replace(/-+/g, '-')
        .replace(/^-|-$/g, '')
        || `device-${Date.now()}`;
      createDeviceMutation.mutate({
        id,
        name: newDeviceName,
        device_type: newDeviceType,
      });
    }
  };

  const handleDeleteDevice = (deviceId) => {
    // Using confirm for simplicity; in production, consider a custom modal
    const confirmed = window.confirm('Are you sure you want to delete this device? This action cannot be undone.');
    if (confirmed) {
      deleteDeviceMutation.mutate(deviceId);
    }
  };

  // Merge device and collector stats
  const enrichedDevices = devices.map(device => {
    const stats = collectorStats.find(s => s.device_id === device.id);
    return {
      ...device,
      collectors_count: stats?.collectors_count || 0,
      recent_activity: stats?.recent_activity || false,
    };
  });

  const isLoading = devicesLoading || statsLoading;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-96">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Devices</h1>
        <p className="text-gray-600">Manage your data collection devices</p>
      </div>

      {/* Add Device Button */}
      <div className="mb-6">
        <button
          onClick={() => setShowAddDevice(!showAddDevice)}
          className="btn-primary flex items-center gap-2"
        >
          <Plus size={20} />
          Add Device
        </button>
      </div>

      {/* Add Device Form */}
      {showAddDevice && (
        <div className="card mb-6 bg-blue-50 border-2 border-blue-200">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Add New Device</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Device Name
              </label>
              <input
                type="text"
                value={newDeviceName}
                onChange={(e) => setNewDeviceName(e.target.value)}
                placeholder="My Laptop"
                className="input-field"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Device Type
              </label>
              <select
                value={newDeviceType}
                onChange={(e) => setNewDeviceType(e.target.value)}
                className="input-field"
              >
                <option value="desktop">Desktop</option>
                <option value="laptop">Laptop</option>
                <option value="mobile">Mobile</option>
                <option value="tablet">Tablet</option>
                <option value="server">Server</option>
              </select>
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleAddDevice}
              disabled={createDeviceMutation.isPending}
              className="btn-primary"
            >
              {createDeviceMutation.isPending ? 'Creating...' : 'Create Device'}
            </button>
            <button
              onClick={() => setShowAddDevice(false)}
              className="btn-secondary"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Devices List */}
      {enrichedDevices.length === 0 ? (
        <div className="card text-center py-12">
          <Monitor className="mx-auto mb-4 text-gray-400" size={48} />
          <p className="text-gray-600 text-lg mb-4">No devices registered</p>
          <p className="text-gray-500 text-sm">Add your first device to start collecting data</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {enrichedDevices.map((device) => {
            const DeviceIcon = deviceIcons[device.device_type] || Monitor;
            
            return (
              <div key={device.id} className="card hover:shadow-lg transition-shadow">
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-start gap-4">
                    <div className={`w-14 h-14 rounded-lg flex items-center justify-center ${
                      device.recent_activity ? 'bg-green-100' : 'bg-gray-100'
                    }`}>
                      <DeviceIcon className={device.recent_activity ? 'text-green-600' : 'text-gray-600'} size={28} />
                    </div>
                    <div>
                      <h3 className="text-lg font-semibold text-gray-900">{device.name || 'Unnamed Device'}</h3>
                      <p className="text-sm text-gray-500 capitalize">{device.device_type || device.type || "unknown"}</p>
                      
                      {/* Status Badge */}
                      <div className="flex items-center gap-2 mt-2">
                        {device.recent_activity ? (
                          <span className="flex items-center gap-1 px-2 py-1 bg-green-100 text-green-700 rounded-full text-xs font-medium">
                            <Activity size={12} />
                            Active
                          </span>
                        ) : (
                          <span className="flex items-center gap-1 px-2 py-1 bg-gray-100 text-gray-600 rounded-full text-xs font-medium">
                            <AlertCircle size={12} />
                            Inactive
                          </span>
                        )}
                        
                        <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded-full text-xs font-medium">
                          {device.collectors_count} {device.collectors_count === 1 ? 'Collector' : 'Collectors'}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex gap-2">
                    <button
                      onClick={() => rotateKeyMutation.mutate(device.id)}
                      className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                      title="Rotate API Key"
                    >
                      <RefreshCw size={18} />
                    </button>
                    <button
                      onClick={() => handleDeleteDevice(device.id)}
                      className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                      title="Delete Device"
                    >
                      <Trash2 size={18} />
                    </button>
                  </div>
                </div>

                {/* Device Details */}
                <div className="border-t border-gray-200 pt-4 mt-4">
                  <div className="grid grid-cols-1 gap-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-600">Device ID:</span>
                      <span className="text-gray-900 font-mono text-xs">{device.id}</span>
                    </div>
                    {device.last_cursor && (
                      <div className="flex justify-between">
                        <span className="text-gray-600">Last Sync:</span>
                        <span className="text-gray-900">{new Date(device.last_cursor).toLocaleString()}</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default Devices;
