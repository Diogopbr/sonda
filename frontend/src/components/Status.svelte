<script lang="ts">
  import type { Tone } from '../lib/status';
  let { label, tone = 'quiet' }: { label: string; tone?: Tone } = $props();
</script>

<span class={`status ${tone}`}><span class="status-dot" aria-hidden="true"></span>{label}</span>
