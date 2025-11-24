import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { devicesAPI, configAPI, healthAPI } from '../services/api';
import { Settings as SettingsIcon, Monitor, Plus, Trash2, RefreshCw, Check, X, Activity } from 'lucide-react';

const Settings = () => {
  const [activeTab, setActiveTab] = useState('devices');
  const [showAddDevice, setShowAddDevice] = useState(false);
  const [newDeviceName, setNewDeviceName] = useState('');
  const [newDeviceType, setNewDeviceType] = useState('desktop');
  const queryClient = useQueryClient();

  // Devices
  const { data: devices = [], isLoading: devicesLoading } = useQuery({
    queryKey: ['devices'],
    queryFn: devicesAPI.getDevices,
  });

  const createDeviceMutation = useMutation({
    mutationFn: (device) => devicesAPI.createDevice(device),
    onSuccess: () => {
      queryClient.invalidateQueries(['devices']);
      setShowAddDevice(false);
      setNewDeviceName('');
      setNewDeviceType('desktop');
    },
  });

  const deleteDeviceMutation = useMutation({
    mutationFn: (deviceId) => devicesAPI.deleteDevice(deviceId),
    onSuccess: () => {
      queryClient.invalidateQueries(['devices']);
    },
  });

  const rotateKeyMutation = useMutation({
    mutationFn: (deviceId) => devicesAPI.rotateKey(deviceId),
    onSuccess: () => {
      queryClient.invalidateQueries(['devices']);
    },
  });

  // Config
  const { data: config = [], isLoading: configLoading } = useQuery({
    queryKey: ['config'],
    queryFn: configAPI.getConfig,
  });

  // Health
  const { data: health, isLoading: healthLoading, refetch: refetchHealth } = useQuery({
    queryKey: ['health'],
    queryFn: healthAPI.getHealth,
  });

  const handleAddDevice = () => {
    if (newDeviceName.trim()) {
      createDeviceMutation.mutate({
        name: newDeviceName,
        type: newDeviceType,
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

  const tabs = [
    { id: 'devices', name: 'Devices', icon: Monitor },
    { id: 'config', name: 'Configuration', icon: SettingsIcon },
    { id: 'health', name: 'System Health', icon: Activity },
  ];

  return (
    <div className="max-w-6xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Settings</h1>
        <p className="text-gray-600">Manage your LifeLog configuration</p>
      </div>

      {/* Tabs */}
      <div className="bg-white rounded-lg shadow-md mb-6">
        <div className="border-b border-gray-200">
          <nav className="flex -mb-px">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 px-6 py-4 border-b-2 font-medium text-sm transition-colors ${
                    activeTab === tab.id
                      ? 'border-blue-600 text-blue-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`}
                >
                  <Icon size={20} />
                  {tab.name}
                </button>
              );
            })}
          </nav>
        </div>

        <div className="p-6">
          {/* Devices Tab */}
          {activeTab === 'devices' && (
            <div>
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-semibold text-gray-900">Registered Devices</h2>
                <button
                  onClick={() => setShowAddDevice(!showAddDevice)}
                  className="btn-primary flex items-center gap-2"
                >
                  <Plus size={20} />
                  Add Device
                </button>
              </div>

              {showAddDevice && (
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-6 mb-6">
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

              {devicesLoading ? (
                <div className="flex items-center justify-center py-12">
                  <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
                </div>
              ) : devices.length === 0 ? (
                <p className="text-gray-500 text-center py-12">No devices registered</p>
              ) : (
                <div className="space-y-4">
                  {devices.map((device) => (
                    <div key={device.id} className="border border-gray-200 rounded-lg p-4">
                      <div className="flex items-start justify-between">
                        <div className="flex items-start gap-3">
                          <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center">
                            <Monitor className="text-blue-600" size={24} />
                          </div>
                          <div>
                            <h3 className="font-semibold text-gray-900">{device.name || 'Unnamed Device'}</h3>
                            <p className="text-sm text-gray-500 capitalize">{device.type || 'unknown'}</p>
                            <p className="text-xs text-gray-400 mt-1">ID: {device.id}</p>
                            {device.last_cursor && (
                              <p className="text-xs text-gray-400">
                                Last sync: {new Date(device.last_cursor).toLocaleString()}
                              </p>
                            )}
                          </div>
                        </div>
                        <div className="flex gap-2">
                          <button
                            onClick={() => rotateKeyMutation.mutate(device.id)}
                            className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                            title="Rotate API Key"
                          >
                            <RefreshCw size={20} />
                          </button>
                          <button
                            onClick={() => handleDeleteDevice(device.id)}
                            className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                            title="Delete Device"
                          >
                            <Trash2 size={20} />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Configuration Tab */}
          {activeTab === 'config' && (
            <div>
              <h2 className="text-xl font-semibold text-gray-900 mb-6">System Configuration</h2>
              {configLoading ? (
                <div className="flex items-center justify-center py-12">
                  <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
                </div>
              ) : config.length === 0 ? (
                <p className="text-gray-500 text-center py-12">No configuration items found</p>
              ) : (
                <div className="space-y-4">
                  {config.map((item) => (
                    <div key={item.key} className="border border-gray-200 rounded-lg p-4">
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <h3 className="font-semibold text-gray-900">{item.key}</h3>
                          <p className="text-sm text-gray-600 mt-1">{item.description || 'No description'}</p>
                          <p className="text-sm text-gray-800 mt-2 font-mono bg-gray-50 p-2 rounded">
                            {item.value}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Health Tab */}
          {activeTab === 'health' && (
            <div>
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-semibold text-gray-900">System Health</h2>
                <button
                  onClick={() => refetchHealth()}
                  className="btn-secondary flex items-center gap-2"
                >
                  <RefreshCw size={20} />
                  Refresh
                </button>
              </div>

              {healthLoading ? (
                <div className="flex items-center justify-center py-12">
                  <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
                </div>
              ) : !health ? (
                <p className="text-gray-500 text-center py-12">Unable to fetch health data</p>
              ) : (
                <div className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="card">
                      <div className="flex items-center gap-3">
                        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                          health.status === 'healthy' ? 'bg-green-100' : 'bg-red-100'
                        }`}>
                          {health.status === 'healthy' ? (
                            <Check className="text-green-600" size={24} />
                          ) : (
                            <X className="text-red-600" size={24} />
                          )}
                        </div>
                        <div>
                          <p className="text-sm text-gray-600">Status</p>
                          <p className="text-xl font-semibold text-gray-900 capitalize">
                            {health.status || 'Unknown'}
                          </p>
                        </div>
                      </div>
                    </div>

                    <div className="card">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
                          <Activity className="text-blue-600" size={24} />
                        </div>
                        <div>
                          <p className="text-sm text-gray-600">Version</p>
                          <p className="text-xl font-semibold text-gray-900">
                            {health.version || 'N/A'}
                          </p>
                        </div>
                      </div>
                    </div>

                    <div className="card">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
                          <SettingsIcon className="text-purple-600" size={24} />
                        </div>
                        <div>
                          <p className="text-sm text-gray-600">Timestamp</p>
                          <p className="text-sm font-medium text-gray-900">
                            {health.timestamp ? new Date(health.timestamp).toLocaleString() : 'N/A'}
                          </p>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="card">
                    <h3 className="text-lg font-semibold text-gray-900 mb-4">Health Details</h3>
                    <pre className="bg-gray-50 p-4 rounded-lg overflow-x-auto text-sm">
                      {JSON.stringify(health, null, 2)}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Settings;
