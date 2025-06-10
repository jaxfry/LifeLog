import { CardContent, CardHeader, CardTitle } from '../../ui';

export default function SampleWidget() {
  return (
    <>
      <CardHeader>
        <CardTitle>Sample Widget</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-on-surface-variant">Example dashboard content.</p>
      </CardContent>
    </>
  );
}
