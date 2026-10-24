# The memory of the machine: how it is managed

Hardware: 3.7 GB of physical RAM, and the pages of zram and the swap
file give the applications the room of ~15 GB.  This file is what was
decided and what is in place; it is the story from the notes, kept in
the repository so it travels with the shell.

## Three layers of swap

1. **zram0: 8 GB in RAM, zstd, priority 100.**
   A compressed ramdisk of swap: the kernel pushes the cold pages of
   the machine into it and they take a quarter of their room.  The
   ratio on this workload sits around 2.5-4:1.

   Config in `/etc/systemd/zram-generator.conf`:

   ```
   [zram0]
   zram-size = 8192
   zram-resident-limit = 2048
   compression-algorithm = zstd
   swap-priority = 100
   ```

   The device cannot be grown while in use.  To change its size:
   `swapoff /dev/zram0`, then
   `sudo systemctl restart systemd-zram-setup@zram0.service`
   (resort to `echo 1 > /sys/block/zram0/reset` if it complains that
   the device is busy).

2. **/swapfile: 8 GB on the SSD, priority 90.**
   The last resort, in `/etc/fstab`
   (`/swapfile none swap defaults,pri=90 0 0`).

   It also receives the pages of zram0 while its device is being
   recreated, which makes those restarts invisible to the desktop.

3. **The kernel decides which of them to use**: priority 100 before 90.
   Watch the split with `swapon --show` and
   `cat /sys/block/zram0/mm_stat`
   (columns: original bytes, compressed bytes, RAM used, limit, max,
   same pages, compacted, huge pages).

## The sysctls that keep the swap moving

`/etc/sysctl.d/99-zram.conf`:

```
vm.swappiness = 100
vm.page-cluster = 0
vm.vfs_cache_pressure = 50
vm.min_free_kbytes = 98304
vm.watermark_scale_factor = 125
```

* `swappiness = 100` - the top of the scale: anon pages go to zram as
  eagerly as file reads do.  With zram that is what one wants; the
  pages come back out of compression cheaply.
* `page-cluster = 0` - pages moved one by one, no read-ahead for a
  swap that is actually RAM.
* `vfs_cache_pressure = 50` - keep the dentry/inode caches a little
  against disk read eviction.
* `min_free_kbytes = 98304` - a hard 96 MB of free memory: reclaim of
  the cold pages into zram starts before the machine is truly full,
  which is the closest the kernel gets to "use zram before the RAM".
* `watermark_scale_factor = 125` - the background reclaimer stays on
  top of the free memory instead of sleeping through bursts.

zram can never be consumed *before* the physical RAM - it *is* RAM -
but these turn on the eviction early enough that the machine behaves
like it had the extra memory.

## systemd-oomd: the pressure kills the right process

Enabled on 2026-10-23, config drop-ins:

* `/etc/systemd/system/user@.service.d/oomd-delegate.conf` -
  `Delegate=destroy-process`: every service of the user sits in its
  own cgroup, so the kill of a runaway stops with that service.
* `/etc/systemd/system/user.slice.d/oomd.conf` -
  `ManagedOOMMemoryPressure=kill`,
  `ManagedOOMMemoryPressureLimit=70%`: at 70% of the memory pressure
  of the slice, oomd kills the cgroup with the most pressure.

What this buys: when whisper or ollama or a browser eats the room, the
offender is killed on its own instead of the shell or the whole log
idle dying with the machine.

## The shell itself stays small

* One process hosts every panel (about 340 MB live today) instead of
  one per panel, which matters on this hardware.
* The helper at `~/.local/bin/macshell-toplevels` asks the compositor
  over its own connection and closes; the shell keeps no connections.
* Caches of icons, weather and friendlies are all in-process with TTLs
  and a file behind themtwice, not daemons.

## What was tried and left behind

* `zram-resident-limit` in zram-generator was read by the 2024+
  versions into `mem_limit` - a cap of the *device*, not a cap on how
  much of the physical RAM the compressed pages may keep.  Do not
  confuse the two; total resident control is not a thing the
  generator can do.
* Growing zram0 in place fails with EBUSY while it has an owner;
  swapoff first, always.
* A second zram device cannot appear while the module was loaded with
  `num_devices=1`; the kernel parameter would have to change for that,
  and the booting of a new module while swap is running is more risk
  than it is worth.

## The numbers as they stand today

```
/dev/zram0  8G  priority 100   ~2.1 GB of pages, ~830 MB after zstd
/swapfile   8G  priority  90   the overflow beyond that
free: ~450 MB normally free, mem pressure served by the creation above
```
