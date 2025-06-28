import DashboardLayout from "@/layouts/DashboardLayout";
import TodaysSummaryCard from '@/components/TodaysSummaryCard';
import YesterdaysSummaryCard from '@/components/YesterdaysSummaryCard';

export default function DashboardPage() {
  return (
    <DashboardLayout>
      <div className="container mx-auto p-4 md:p-6 lg:p-8">
        <h1 className="text-3xl font-bold mb-6 text-gray-800 dark:text-white">Dashboard</h1>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <div className="md:col-span-2 lg:col-span-2">
            <TodaysSummaryCard className="h-full" />
          </div>
          <div className="lg:col-span-1">
            <YesterdaysSummaryCard className="h-full" />
          </div>
          <div className="bg-gray-100 dark:bg-gray-800 p-6 rounded-lg shadow hover:shadow-md transition-shadow">
            <h2 className="text-xl font-semibold mb-3 text-gray-700 dark:text-gray-300">Future Widget 1</h2>
            <p className="text-gray-600 dark:text-gray-400">Content for another dashboard widget will go here.</p>
          </div>
          <div className="bg-gray-100 dark:bg-gray-800 p-6 rounded-lg shadow hover:shadow-md transition-shadow">
            <h2 className="text-xl font-semibold mb-3 text-gray-700 dark:text-gray-300">Future Widget 2</h2>
            <p className="text-gray-600 dark:text-gray-400">More dashboard insights coming soon!</p>
          </div>
          <div className="bg-gray-100 dark:bg-gray-800 p-6 rounded-lg shadow hover:shadow-md transition-shadow">
            <h2 className="text-xl font-semibold mb-3 text-gray-700 dark:text-gray-300">Future Widget 3</h2>
            <p className="text-gray-600 dark:text-gray-400">Additional data visualizations will appear here.</p>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
