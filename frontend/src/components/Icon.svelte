<script lang="ts">
  let {
    name,
    size = 20,
  }: {
    name: 'arrow' | 'refresh' | 'pause' | 'play' | 'close' | 'external' | 'check';
    size?: number;
  } = $props();
</script>

<svg
  width={size}
  height={size}
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="1.8"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  {#if name === 'arrow'}<path d="M4 12h15M13 6l6 6-6 6" />
  {:else if name === 'refresh'}<path d="M20 10a8 8 0 1 0-2 8M20 4v6h-6" />
  {:else if name === 'pause'}<path d="M8 5v14M16 5v14" />
  {:else if name === 'play'}<path d="m8 5 11 7-11 7V5Z" />
  {:else if name === 'close'}<path d="m6 6 12 12M18 6 6 18" />
  {:else if name === 'external'}<path d="M14 4h6v6M20 4 10 14M10 4H4v16h16v-6" />
  {:else}<path d="m5 12 4 4 10-10" />{/if}
</svg>
