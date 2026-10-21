<template>
  <header class="header">
    <div class="logo" aria-label="ArtBrief AI">
      <svg class="mark" viewBox="0 0 32 32" aria-hidden="true">
        <rect width="32" height="32" rx="9" fill="currentColor" />
        <path d="M9 23 16 8l7 15M12 18.5h8" fill="none" stroke="var(--bg)" stroke-width="2.4"
          stroke-linecap="round" stroke-linejoin="round" />
      </svg>
      <span class="name">ArtBrief</span>
    </div>
  </header>
</template>

<style scoped>
.header {
  padding: 18px 24px;
}

.logo {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: var(--accent-strong);
}

.mark {
  width: 30px;
  height: 30px;
}

.name {
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text);
}
</style>
