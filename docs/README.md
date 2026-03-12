# Hermes Documentation

Welcome to the Hermes documentation. Hermes is an alert routing and distribution system that solves Alertmanager's limitations with OR matching and many-to-many alert routing.

## Documentation Sections

### Guides

Comprehensive guides for configuring and using Hermes.

- [Getting Started Guide](tutorials/getting-started.md) - Installation and basic setup
- [Alert Routing Guide](tutorials/basic-alert-routing.md) - Configuring routing rules and match patterns
- [Alert Grouping Guide](tutorials/group-alerts.md) - Combining similar alerts into single notifications
- [Multiple Destinations Guide](tutorials/multiple-destinations.md) - Routing to Slack, Discord, and more
- [Advanced Configuration Guide](tutorials/advanced-routing.md) - Complex patterns, deduplication windows, and production setups

### Concepts

Deep dives into Hermes architecture and how it works. Read these to understand the "why" behind the configuration.

- [Routing and Groups](concepts/routing-and-groups.md) - How OR routing works vs Alertmanager
- [Deduplication](concepts/deduplication.md) - Fingerprinting, TTL, and deduplication windows
- [Templating](concepts/templating.md) - Jinja2 template syntax guide
- [State Management](concepts/state-management.md) - Redis vs in-memory state

### Examples

Complete, working configuration files for real-world scenarios.

- [simple-config.yaml](examples/simple-config.yaml) - Basic setup for first-time users
- [multi-team-config.yaml](examples/multi-team-config.yaml) - Production-like multi-team routing
- [grouped-alerts-config.yaml](examples/grouped-alerts-config.yaml) - Grouped alert examples

## Quick Reference

| Need | Go to |
|------|-------|
| Getting started | [Getting Started Guide](tutorials/getting-started.md) |
| Configure Slack/Discord | [Alert Routing Guide](tutorials/basic-alert-routing.md) |
| Reduce notification noise | [Alert Grouping Guide](tutorials/group-alerts.md) |
| Multiple destinations | [Multiple Destinations Guide](tutorials/multiple-destinations.md) |
| Advanced configuration | [Advanced Configuration Guide](tutorials/advanced-routing.md) |
| How routing works | [Routing and Groups](concepts/routing-and-groups.md) |
| How deduplication works | [Deduplication](concepts/deduplication.md) |
| How to customize messages | [Templating](concepts/templating.md) |
| I need a config example | [Examples](examples/) |

## Additional Resources

- [Architecture Documentation](architecture.md) - Detailed system architecture
- [Alertmanager Integration](alertmanager-integration.md) - Configure Alertmanager to send to Hermes
- [Troubleshooting Guide](troubleshooting.md) - Debug common issues
- [Main README](../README.md) - Quick start, installation, deployment

## Search Tips

Looking for something specific?

- **Config examples**: Check [examples/](examples/)
- **Match patterns**: See [Routing and Groups](concepts/routing-and-groups.md) or [Basic Alert Routing](tutorials/basic-alert-routing.md)
- **Template variables**: See [Templating](concepts/templating.md)
- **Deduplication settings**: See [Deduplication](concepts/deduplication.md)
- **Deployment options**: See [State Management](concepts/state-management.md) or main [README](../README.md)

## Need Help?

- Check the [Troubleshooting Guide](troubleshooting.md) for common issues
- Review [Architecture](architecture.md) for system details
- See [Alertmanager Integration](alertmanager-integration.md) for webhook setup
