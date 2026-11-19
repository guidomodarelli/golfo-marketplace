# Async effect cancellation

Use this pattern when the client must fetch inside a `useEffect` (see the server-first rules in `SKILL.md` first). `AbortController` is the primary mechanism; the `isActive` guard is a safety net for late microtasks or non-abortable work.

```js
useEffect(() => {
  const controller = new AbortController();
  let isActive = true;

  async function loadProfile() {
    try {
      const profile = await fetchUserProfile(userId, { signal: controller.signal });
      if (!isActive) return;
      setProfile(profile);
    } catch (error) {
      if (!isActive) return;
      if (isCancellationError(error)) return;
      logger.error(`UserProfile:loadProfile failed (userId=${userId})`, error);
      setLoadError(true);
    }
  }

  loadProfile();

  return () => {
    isActive = false;
    controller.abort();
  };
}, [userId]);

function isCancellationError(error) {
  return (
    error?.name === 'AbortError' ||
    error?.name === 'CanceledError' ||
    error?.code === 'ERR_CANCELED'
  );
}
```

## Client wrapper without `signal`

If the project's REST client does not accept a cancellation signal, extend its options to accept `{ signal }` and forward it to the underlying request (`fetch(url, { signal })` or `axios.get(url, { signal })`). Do not work around it with a boolean flag: the stale request keeps running and its response can still arrive.
