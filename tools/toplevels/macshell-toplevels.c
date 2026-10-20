/*
 * macshell-toplevels -- list the compositor's toplevels as JSON.
 *
 * River Classic does not ship an introspection command in riverctl, so the
 * shell asks the wlr-foreign-toplevel protocol directly.  The output is the
 * same shape wlrctl uses, so the shell can parse it with json.loads().
 *
 *   [{"app_id": "foot", "title": "zsh", "activated": true}, ...]
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>

#include <wayland-client.h>

#include "wlr-toplevel-client-protocol.h"

#define MAX_TOPLEVELS 128

struct toplevel {
	struct zwlr_foreign_toplevel_handle_v1 *handle;
	char *app_id;
	char *title;
	bool activated;
};

static struct wl_seat *seat = NULL;

static struct toplevel toplevels[MAX_TOPLEVELS];
static int toplevel_count = 0;

static void handle_title(void *data, struct zwlr_foreign_toplevel_handle_v1 *handle,
                         const char *title) {
	struct toplevel *t = data;
	free(t->title);
	t->title = strdup(title);
}

static void handle_app_id(void *data, struct zwlr_foreign_toplevel_handle_v1 *handle,
                          const char *app_id) {
	struct toplevel *t = data;
	free(t->app_id);
	t->app_id = strdup(app_id);
}

static void handle_output_enter(void *data,
                                struct zwlr_foreign_toplevel_handle_v1 *handle,
                                struct wl_output *output) {}
static void handle_output_leave(void *data,
                                struct zwlr_foreign_toplevel_handle_v1 *handle,
                                struct wl_output *output) {}
static void handle_parent(void *data,
                          struct zwlr_foreign_toplevel_handle_v1 *handle,
                          struct zwlr_foreign_toplevel_handle_v1 *parent) {}
static void handle_done(void *data, struct zwlr_foreign_toplevel_handle_v1 *handle) {}
static void handle_closed(void *data, struct zwlr_foreign_toplevel_handle_v1 *handle) {
	struct toplevel *t = data;
	t->handle = NULL;
}

static void handle_state(void *data, struct zwlr_foreign_toplevel_handle_v1 *handle,
                         struct wl_array *states) {
	struct toplevel *t = data;
	uint32_t *state;
	t->activated = false;
	wl_array_for_each(state, states) {
		/* 2 == activated */
		if (*state == 2) {
			t->activated = true;
		}
	}
}

static const struct zwlr_foreign_toplevel_handle_v1_listener handle_listener = {
	.title = handle_title,
	.app_id = handle_app_id,
	.output_enter = handle_output_enter,
	.output_leave = handle_output_leave,
	.parent = handle_parent,
	.state = handle_state,
	.done = handle_done,
	.closed = handle_closed,
};

static void manager_toplevel(void *data,
                             struct zwlr_foreign_toplevel_manager_v1 *manager,
                             struct zwlr_foreign_toplevel_handle_v1 *handle) {
	if (toplevel_count >= MAX_TOPLEVELS) {
		return;
	}
	struct toplevel *t = &toplevels[toplevel_count++];
	memset(t, 0, sizeof(*t));
	t->handle = handle;
	t->app_id = strdup("");
	t->title = strdup("");
	zwlr_foreign_toplevel_handle_v1_add_listener(handle, &handle_listener, t);
}

static void manager_finished(void *data,
                             struct zwlr_foreign_toplevel_manager_v1 *manager) {}

static const struct zwlr_foreign_toplevel_manager_v1_listener manager_listener = {
	.toplevel = manager_toplevel,
	.finished = manager_finished,
};

static void registry_global(void *data, struct wl_registry *registry,
                            uint32_t name, const char *interface, uint32_t version) {
	if (strcmp(interface, wl_seat_interface.name) == 0 && seat == NULL) {
		seat = wl_registry_bind(registry, name, &wl_seat_interface, version < 5 ? version : 5);
		return;
	}
	if (strcmp(interface, zwlr_foreign_toplevel_manager_v1_interface.name) == 0) {
		struct zwlr_foreign_toplevel_manager_v1 *manager =
			wl_registry_bind(registry, name,
			                 &zwlr_foreign_toplevel_manager_v1_interface,
			                 version < 3 ? version : 3);
		zwlr_foreign_toplevel_manager_v1_add_listener(manager, &manager_listener, NULL);
	}
}

static void registry_global_remove(void *data, struct wl_registry *registry,
                                   uint32_t name) {}

static const struct wl_registry_listener registry_listener = {
	.global = registry_global,
	.global_remove = registry_global_remove,
};

static void print_json_string(const char *text) {
	putchar('"');
	for (const unsigned char *p = (const unsigned char *)text; *p; p++) {
		switch (*p) {
		case '"': fputs("\\\"", stdout); break;
		case '\\': fputs("\\\\", stdout); break;
		case '\n': fputs("\\n", stdout); break;
		case '\t': fputs("\\t", stdout); break;
		case '\r': fputs("\\r", stdout); break;
		default:
			if (*p < 0x20) {
				printf("\\u%04x", *p);
			} else {
				putchar(*p);
			}
		}
	}
	putchar('"');
}

int main(int argc, char **argv) {
	const char *close_match = NULL;
	const char *activate_match = NULL;
	if (argc >= 3 && strcmp(argv[1], "--close") == 0) {
		close_match = argv[2];
	}
	if (argc >= 3 && strcmp(argv[1], "--activate") == 0) {
		activate_match = argv[2];
	}

	struct wl_display *display = wl_display_connect(NULL);
	if (!display) {
		fprintf(stderr, "macshell-toplevels: cannot connect to the display\n");
		return 1;
	}

	struct wl_registry *registry = wl_display_get_registry(display);
	wl_registry_add_listener(registry, &registry_listener, NULL);

	/* the first roundtrip delivers the globals, the second the toplevels */
	wl_display_roundtrip(display);
	wl_display_roundtrip(display);

	putchar('[');
	bool first = true;
	for (int i = 0; i < toplevel_count; i++) {
		struct toplevel *t = &toplevels[i];
		if (!t->title) {
			continue;
		}
		if (activate_match && t->handle && strstr(t->title, activate_match)) {
			if (seat != NULL) {
				zwlr_foreign_toplevel_handle_v1_activate(t->handle, seat);
			}
			wl_display_roundtrip(display);
			continue;
		}
		if (close_match && t->handle && strstr(t->title, close_match)) {
			zwlr_foreign_toplevel_handle_v1_close(t->handle);
			wl_display_roundtrip(display);
			continue;
		}
		if (!first) {
			putchar(',');
		}
		first = false;
		fputs("{\"app_id\": ", stdout);
		print_json_string(t->app_id ? t->app_id : "");
		fputs(", \"title\": ", stdout);
		print_json_string(t->title);
		printf(", \"activated\": %s}", t->activated ? "true" : "false");
	}
	putchar(']');
	putchar('\n');

	wl_display_disconnect(display);
	return 0;
}
